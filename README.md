# redhat-monitoring

Prometheus + Alertmanager + Grafana (Tablero DevOps (MDT) + Metricas Fuse / AMQ / Apicast 3scale)

- __[Paso 1](#instalar-minishift-okd)__ - Procedimiento de instalación de Minishift (OKD).
- __[Paso 2](#prometheus)__ - Procedimiento de instalación Prometheus.
- __[Paso 3](#exporters-mdt)__ - Procedimiento de instalación Exporter tablero DevOps (MDT).
- __[Paso 4](#grafana)__ - Procedimiento de instalación Grafana.
- __[Paso 5](#ejemplo)__ - Despliegue aplicación de ejemplo (AMQ y Apicast)

## instalar minishift (okd)

### macosx

    wget https://github.com/minishift/minishift/releases/download/v1.34.2/minishift-1.34.2-darwin-amd64.tgz
    tar -tlvf minishift-1.34.2-darwin-amd64.tgz
    sudo cp minishift-1.34.2-darwin-amd64/minishift /usr/local/bin/minishift
    sudo chmod 777 /usr/local/bin/minishift

### driver (hyperkit)

    sudo curl -L  https://github.com/machine-drivers/docker-machine-driver-hyperkit/releases/download/v1.0.0/docker-machine-driver-hyperkit -o /usr/local/bin/docker-machine-driver-hyperkit
    sudo chown root:wheel /usr/local/bin/docker-machine-driver-hyperkit
    sudo chmod u+s,+x /usr/local/bin/docker-machine-driver-hyperkit

### start

    minishift addon enable admin-user
    minishift addon enable anyuid
    minishift addon enable xpaas
    minishift addon enable registry-route
    minishift addon enable redhat-registry-login

    minishift start --cpus=4 --memory=10GB --disk-size=60GB --vm-driver hyperkit --skip-registration
    minishift openshift config set --patch '{"jenkinsPipelineConfig":{"autoProvisionEnabled":true}}'

#### Adding the cluster admin role, to the 'admin' user in Minishift

    minishift ssh
    docker exec -it origin bash
    oc --config=/var/lib/origin/openshift.local.config/master/admin.kubeconfig  adm policy  --as system:admin add-cluster-role-to-user cluster-admin admin
    exit
    exit

## instalar stack monitoreo

    oc login https://$(minishift ip):8443 -u admin
    oc create route edge --service=docker-registry -n default

---

    PROJECT=redhat-monitoring
    oc new-project ${PROJECT}

### prometheus

    oc new-app -f prometheus.yml -p NAMESPACE=${PROJECT} -p PROMETHEUS_DATA_STORAGE_SIZE=1Gi -p ALERTMANAGER_DATA_STORAGE_SIZE=1Gi

### exporters (pelorus / MDT)

#### creamos las imágenes

    docker build -q --rm -t pelorus/committime ./exporters/committime/
    docker build -q --rm -t pelorus/deploytime ./exporters/deploytime/
    docker build -q --rm -t pelorus/failure ./exporters/failure/

#### exportarmos imágenes a openshift

    oc login https://$(minishift ip):8443 -u admin
    docker login -u admin -p $(oc whoami -t) docker-registry-default.$(minishift ip).nip.io

    docker tag pelorus/committime docker-registry-default.$(minishift ip).nip.io/openshift/committime:latest
    docker push docker-registry-default.$(minishift ip).nip.io/openshift/committime:latest

    docker tag pelorus/deploytime docker-registry-default.$(minishift ip).nip.io/openshift/deploytime:latest
    docker push docker-registry-default.$(minishift ip).nip.io/openshift/deploytime:latest

    docker tag pelorus/failure docker-registry-default.$(minishift ip).nip.io/openshift/failure:latest
    docker push docker-registry-default.$(minishift ip).nip.io/openshift/failure:latest

#### config

    GITHUB_USER=damianlezcano
    GITHUB_TOKEN=2470742754553ec8222713c1cb82ddaf22a57748

    JIRA_TOKEN=CiMYWbI04wG2W5B0Ze589E3C
    JIRA_USER=lezcano.da@gmail.com
    JIRA_SERVER=https://damianlezcano.atlassian.net
    JIRA_PROJECT=AGIL

#### intanciamos los exporters

	oc adm policy add-cluster-role-to-user view system:serviceaccount:redhat-monitoring:default -n ${PROJECT}

    oc new-app committime:latest --name committime-exporter -e APP_FILE=exporter/app.py -e OPENSHIFT_BUILD_NAME=commiter-exporter -e NAMESPACES=app-project1 -e APP_LABEL=app -e LOG_LEVEL=DEBUG -e GITHUB_USER=${GITHUB_USER} -e GITHUB_TOKEN=${GITHUB_TOKEN} -e GITHUB_API_BAK=api.github.com -n ${PROJECT}

    oc new-app deploytime:latest --name deploytime-exporter -e APP_FILE=exporter/app.py -e OPENSHIFT_BUILD_NAME=deploytime-exporter -e NAMESPACES=app-project1 -e APP_LABEL=app -e LOG_LEVEL=DEBUG -n ${PROJECT}

    oc new-app failure:latest --name failure-exporter -e APP_FILE=exporter/app.py -e OPENSHIFT_BUILD_NAME=failure-exporter -e APP_LABEL=app -e LOG_LEVEL=DEBUG -e TOKEN=${JIRA_TOKEN} -e USER=${JIRA_USER} -e SERVER=${JIRA_SERVER} -e PROJECT=${JIRA_PROJECT} -n ${PROJECT}

    oc expose service committime-exporter -n ${PROJECT}
    oc expose service deploytime-exporter -n ${PROJECT}
    oc expose service failure-exporter -n ${PROJECT}

    oc label service committime-exporter job=openshift-state-metrics -n ${PROJECT}
    oc label service deploytime-exporter  job=openshift-state-metrics -n ${PROJECT}
    oc label service failure-exporter job=openshift-state-metrics -n ${PROJECT}

### grafana

    oc create configmap grafana-dashboards --from-file=grafana-dashboard-mdt.json --from-file=grafana-dashboard-fuse.json --from-file=grafana-dashboard-amq.json -n ${PROJECT}
    oc new-app -f grafana.yaml -p NAMESPACE=${PROJECT}

### Ejemplo

#### app-project1 (build jenkins strategy)

Crear secret con credenciales para descargar imagenes de registry.redhat.io

<!--
    oc create secret generic registryredhatiosecret --from-file=.dockerconfigjson=config.json --type=kubernetes.io/dockerconfigjson
    oc secrets link default registryredhatiosecret --for=pull
    oc secrets link builder registryredhatiosecret 
-->

    oc project openshift
    # https://access.redhat.com/RegistryAuthentication
    oc create -f 5318211_okd-secret.yaml
    oc secrets link default 5318211-okd-pull-secret --for=pull
    oc secrets link builder 5318211-okd-pull-secret

Importamos imagenes al namespace openshift:

    oc import-image fuse7/fuse-java-openshift:1.2 --from=registry.redhat.io/fuse7/fuse-java-openshift --confirm
    oc import-image amq7/amq-broker-rhel7-operator:0.13 --from=registry.redhat.io/amq7/amq-broker-rhel7-operator:0.13 --confirm
    oc import-image amq7/amq-broker:7.6 --from=registry.redhat.io/amq7/amq-broker:7.6 --confirm
    oc import-image 3scale-amp2/apicast-gateway-rhel7 --from=registry.redhat.io/3scale-amp2/apicast-gateway-rhel7 --confirm

Configuramos credenciales para que jenkins acceda al repositorio
    
    oc new-project app-project1

    oc create secret generic repository-credentials --from-literal=username=${GITHUB_USER} --from-literal=password=${GITHUB_TOKEN} --type=kubernetes.io/basic-auth -n app-project1

    oc label secret repository-credentials credential.sync.jenkins.openshift.io=true -n app-project1
    
    oc annotate secret repository-credentials 'build.openshift.io/source-secret-match-uri-1=ssh://github.com/*' -n app-project1

Desplegamos AMQ

    oc create -f amq-broker-operator/service_account.yaml -n app-project1
    oc create -f amq-broker-operator/role.yaml -n app-project1
    oc create -f amq-broker-operator/role_binding.yaml -n app-project1
    oc create -f amq-broker-operator/crds/broker_activemqartemis_crd.yaml -n app-project1
    oc create -f amq-broker-operator/crds/broker_activemqartemisaddress_crd.yaml -n app-project1
    oc create -f amq-broker-operator/crds/broker_activemqartemisscaledown_crd.yaml -n app-project1
    oc create -f amq-broker-operator/operator.yaml -n app-project1
    oc create secret generic broker-amq-credentials-secret --from-literal=clusterUser=clusterUser --from-literal=clusterPassword=clusterPassword --from-literal=AMQ_USER=admin --from-literal=AMQ_PASSWORD=admin -n app-project1
    oc create -f amq-broker-operator/crs/broker_activemqartemis_cr.yaml -n app-project1
    oc set env statefulset broker-amq-ss AMQ_ENABLE_METRICS_PLUGIN=true -n app-project1

Desplegamos Fake email para poder visualizar las notificaciones de alertmanager

    oc new-app mailhog/mailhog -n ${PROJECT}
    oc expose svc/mailhog --port=8025 -n ${PROJECT}

Desplegamos app example1

    oc create -f https://raw.githubusercontent.com/damianlezcano/prometheus-example-fuse/master/template.yaml -n app-project1

    oc new-app --template java-app-deploy -p APP_NAME=example1 -p GIT_REPO=https://github.com/damianlezcano/prometheus-example-fuse.git -p GIT_BRANCH=master -n app-project1

    oc start-build example1-pipeline -n app-project1

Desplegamos apicast

    cd apicast
    mvn clean package -DskipTests -s settings.xml
    docker build -t apicat-proxy .

    docker tag apicast-proxy docker-registry-default.$(minishift ip).nip.io/openshift/apicast-proxy:latest
    docker push docker-registry-default.$(minishift ip).nip.io/openshift/apicast-proxy:latest

    oc new-app -f apicast.yml -p APICAST_NAME=apicast-staging -p DEPLOYMENT_ENVIRONMENT=staging -p CONFIGURATION_LOADER=lazy -p EXTENDED_METRICS=true -n app-project1

Generar commit para el tablero DevOps (MDT)

    date > version.txt
    git add .;git commit -m "Cambio en version";git push

Generamos tráfico para el trablero de metricas

    curl --location --request POST 'http://example1-app-project1.${minishift ip}.nip.io/api/say' --header 'Content-Type: text/plain' --data-raw 'World'

_Si se reemplaza 'World' por 'Error' esto genera un error en la ruta camel enviando el mensaje a la DLQ, permitiendo activar luego de mas de 10 intentos una de las reglas configuradas en prometheus y generando finalmente una notificacion por email (Ir a http://mailhog-${PROJECT}.${minishift ip}.nip.io/)_











curl http://mock-rest:8080/transactions/authrep.xml
curl http://mock-rest.app-project1.svc:8080/transactions/authrep.xml
curl http://mock-rest-app-project1.192.168.64.14.nip.io/transactions/authrep.xml


oc delete service "mock-rest"
oc delete deploymentconfigs.apps.openshift.io "apicast-staging"
oc delete configmaps "mock-rest-services-config"
oc delete configmap "mock-rest-transactions-config"
oc delete configmaps "mock-rest-admin-config"
oc delete secrets "apicast-configuration-url-secret"
oc delete services "apicast-staging"
oc delete routes.route.openshift.io "apicast-staging"

oc delete secret apicast-configuration-url-secret;oc create secret generic apicast-configuration-url-secret --from-literal=password=http://c305ade34d4b720fa1ccfe3bfdfa0bb30c2764b108e9187063d663a7fa935016@mock-rest-app-project1.192.168.64.14.nip.io --type=kubernetes.io/basic-auth -n app-project1

sudo python -m SimpleHTTPServer 80 -b 0.0.0.0

minishift delete --force --clear-cache;rm -rf /Users/damianlezcano/.minishift;rm -rf /Users/damianlezcano/.kube

curl http://localhost:9421/metrics
https://medium.com/@joelicious/red-hat-3scale-monitoring-with-prometheus-and-grafana-4e683f3125bb