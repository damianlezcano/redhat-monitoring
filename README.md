# redhat-monitoring

- __[Paso 1](#instalar-minishift-okd)__ - Procedimiento de instalación de Minishift (OKD).
- __[Paso 2](#prometheus)__ - Procedimiento de instalación Prometheus.
- __[Paso 3](#exporters-mdt)__ - Procedimiento de instalación Exporter tablero DevOps (MDT).
- __[Paso 4](#grafana)__ - Procedimiento de instalación Grafana.
- __[Paso 5](#ejemplo)__ - Despliegue aplicación de ejemplo.

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

    minishift addons list
    minishift addon enable admin-user
    minishift addon enable anyuid
    minishift addon enable xpaas
    minishift addon enable registry-route
    minishift addon enable redhat-registry-login
    eval $(minishift oc-env)
    eval $(minishift docker-env)
    minishift openshift config set --patch '{"jenkinsPipelineConfig":{"autoProvisionEnabled":true}}'

---

    minishift start --cpus=4 --memory=10GB --disk-size=60GB --vm-driver hyperkit --skip-registration

#### Adding the cluster admin role, to the 'admin' user in Minishift

    minishift ssh
    docker exec -it origin bash
    oc --config=/var/lib/origin/openshift.local.config/master/admin.kubeconfig  adm policy  --as system:admin add-cluster-role-to-user cluster-admin admin

## instalar stack monitoreo

    oc login https://$(minishift ip):8443 -u admin
    oc create route edge --service=docker-registry -n default

---

    PROJECT=redhat-monitoring
    oc new-project ${PROJECT}

### prometheus

    oc new-app -f prometheus.yml -p NAMESPACE=${PROJECT} -p PROMETHEUS_DATA_STORAGE_SIZE=1Gi -p ALERTMANAGER_DATA_STORAGE_SIZE=1Gi

### exporters (MDT)

#### creamos las imágenes

    docker build -q --rm -t pelorus/committime ./exporters/committime/
    docker build -q --rm -t pelorus/deploytime ./exporters/deploytime/
    docker build -q --rm -t pelorus/failure ./exporters/failure/

#### exportarmos imágenes a openshift

    oc login https://$(minishift ip):8443 -u admin
    docker login -u admin -p $(oc whoami -t) docker-registry-default.$(minishift ip).nip.io

    docker tag pelorus/committime docker-registry-default.$(minishift ip).nip.io/${PROJECT}/committime:latest
    docker push docker-registry-default.$(minishift ip).nip.io/${PROJECT}/committime:latest

    docker tag pelorus/deploytime docker-registry-default.$(minishift ip).nip.io/${PROJECT}/deploytime:latest
    docker push docker-registry-default.$(minishift ip).nip.io/${PROJECT}/deploytime:latest

    docker tag pelorus/failure docker-registry-default.$(minishift ip).nip.io/${PROJECT}/failure:latest
    docker push docker-registry-default.$(minishift ip).nip.io/${PROJECT}/failure:latest

#### config

    GITHUB_USER=damianlezcano
    GITHUB_TOKEN=xxxx

    JIRA_TOKEN=xxxx
    JIRA_USER=lezcano.da@gmail.com
    JIRA_SERVER=https://damianlezcano.atlassian.net
    JIRA_PROJECT=AGIL

#### intanciamos los exporters

	oc adm policy add-cluster-role-to-user view system:serviceaccount:redhat-monitoring:default -n ${PROJECT}

    oc new-app ${PROJECT}/committime:latest --name committime-exporter -e APP_FILE=exporter/app.py -e OPENSHIFT_BUILD_NAME=commiter-exporter -e NAMESPACES=app-project1 -e APP_LABEL=app -e LOG_LEVEL=DEBUG -e GITHUB_USER=${GITHUB_USER} -e GITHUB_TOKEN=${GITHUB_TOKEN} -e GITHUB_API_BAK=api.github.com -n ${PROJECT}

    oc new-app ${PROJECT}/deploytime:latest --name deploytime-exporter -e APP_FILE=exporter/app.py -e OPENSHIFT_BUILD_NAME=deploytime-exporter -e NAMESPACES=app-project1 -e APP_LABEL=app -e LOG_LEVEL=DEBUG -n ${PROJECT}

    oc new-app ${PROJECT}/failure:latest --name failure-exporter -e APP_FILE=exporter/app.py -e OPENSHIFT_BUILD_NAME=failure-exporter -e APP_LABEL=app -e LOG_LEVEL=DEBUG -e TOKEN=${JIRA_TOKEN} -e USER=${JIRA_USER} -e SERVER=${JIRA_SERVER} -e PROJECT=${JIRA_PROJECT} -n ${PROJECT}

    oc expose service committime-exporter -n ${PROJECT}
    oc expose service deploytime-exporter -n ${PROJECT}
    oc expose service failure-exporter -n ${PROJECT}

    oc label service committime-exporter job=openshift-state-metrics
    oc label service deploytime-exporter  job=openshift-state-metrics
    oc label service failure-exporter job=openshift-state-metrics

### grafana

    oc create configmap grafana-dashboards --from-file=grafana-dashboard-mdt.json --from-file=grafana-dashboard-fuse.json --from-file=grafana-dashboard-amq.json
    oc new-app -f grafana.yaml -p NAMESPACE=${PROJECT}

### Ejemplo

#### app-project1 (build jenkins strategy)

    oc new-project app-project1

Crear secret con credenciales para descargar imagenes de registry.redhat.io

    oc create secret generic registryredhatiosecret --from-file=.dockerconfigjson=config.json --type=kubernetes.io/dockerconfigjson -n openshift
    oc secrets link default registryredhatiosecret --for=pull -n openshift
    oc secrets link builder registryredhatiosecret -n openshift

Importamos imagenes al namespace openshift

    oc project openshift
    oc import-image openshift3/jenkins:2 --from=registry.redhat.io/openshift3/jenkins-2-rhel7 --confirm
    oc import-image fuse7/fuse-java-openshift:1.2 --from=registry.redhat.io/fuse7/fuse-java-openshift --confirm

Configuramos credenciales para que jenkins acceda al repositorio

    oc create secret generic repository-credentials --from-literal=username=${GITHUB_USER} --from-literal=password=${GITHUB_TOKEN} --type=kubernetes.io/basic-auth -n app-project1

    oc label secret repository-credentials credential.sync.jenkins.openshift.io=true -n app-project1
    
    oc annotate secret repository-credentials 'build.openshift.io/source-secret-match-uri-1=ssh://github.com/*' -n app-project1

Desplegamos app example1

    oc create -f https://raw.githubusercontent.com/damianlezcano/prometheus-example-fuse/master/template.yaml -n app-project1

    oc new-app --template java-app-deploy -p APP_NAME=example1 -p GIT_REPO=https://github.com/damianlezcano/prometheus-example-fuse.git -p GIT_BRANCH=master -n app-project1

    oc start-build example1-pipeline

Generar commit para el tablero DevOps (MDT)

    date > version.txt
    git add .;git commit -m "Cambio en version";git push

Generamos tráfico para el trablero de metricas

    curl --location --request POST 'http://example1-app-project1.${minishift ip}.nip.io/api/say' --header 'Content-Type: text/plain' --data-raw 'Hello'