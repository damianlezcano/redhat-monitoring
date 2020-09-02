from collector_base import AbstractCommitCollector
import logging
import pelorus
import requests


class GitHubCommitCollector(AbstractCommitCollector):
    _prefix_pattern = "https://%s/repos/"
    _defaultapi = "api.github.com"
    _prefix = _prefix_pattern % _defaultapi
    _suffix = "/commits/"

    def __init__(self, username, token, namespaces, apps, git_api=None):
        super().__init__(username, token, namespaces, apps, "GitHub", '%Y-%m-%dT%H:%M:%SZ', git_api)
        if self._git_api is not None and len(self._git_api) > 0:
            logging.info("Using non-default API: %s" % (self._git_api))
        else:
            self._git_api = self._defaultapi
        self._prefix = self._prefix_pattern % self._git_api

    def get_commit_time(self, metric):
        """Method called to collect data and send to Prometheus"""
        #logging.info("## collector_github: 0 - metric: %s", metric)
        myurl = metric.repo_url
        #logging.info("## collector_github: 1 - myurl: %s", myurl)
        url_tokens = myurl.split("/")
        #logging.info("## collector_github: 2")
        git_server = url_tokens[2]
        #logging.info("## collector_github: 3")
        # check for gitlab or bitbucket
        if "gitlab" in git_server or "bitbucket" in git_server:
            logging.warn("Skipping non GitHub server, found %s" % (git_server))
            return None

        #logging.info("## collector_github: 4")
        url = self._prefix + url_tokens[3] + "/" + url_tokens[4].split(".")[0] + self._suffix + metric.commit_hash
        #logging.info("## collector_github: 5 - url: %s", url)
        response = requests.get(url, auth=(self._username, self._token))
        #logging.info("## collector_github: 6")
        if response.status_code != 200:
            # This will occur when trying to make an API call to non-Github
            logging.warning("Unable to retrieve commit time for build: %s, hash: %s, url: %s. Got http code: %s" % (
                metric.build_name, metric.commit_hash, url_tokens[2], str(response.status_code)))
        else:
            #logging.info("## collector_github: 7")
            commit = response.json()
            try:
                #logging.info("## collector_github: 8 - commit: %s",commit)
                metric.commit_time = commit['commit']['committer']['date']
                #logging.info("## collector_github: 9")
                metric.commit_timestamp = pelorus.convert_date_time_to_timestamp(metric.commit_time, self._timedate_format)
                #logging.info("## collector_github: 10")
            except Exception:
                logging.error("Failed processing commit time for build %s" % metric.build_name, exc_info=True)
                logging.debug(commit)
                raise
        return metric
