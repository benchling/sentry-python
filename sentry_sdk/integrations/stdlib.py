from sentry_sdk.hub import Hub
from sentry_sdk.integrations import Integration


try:
    from httplib import HTTPConnection  # type: ignore
except ImportError:
    from http.client import HTTPConnection


class StdlibIntegration(Integration):
    identifier = "stdlib"

    @staticmethod
    def setup_once():
        # type: () -> None
        install_httplib()


def install_httplib():
    # type: () -> None
    real_putrequest = HTTPConnection.putrequest
    real_getresponse = HTTPConnection.getresponse

    def putrequest(self, method, url, *args, **kwargs):
        rv = real_putrequest(self, method, url, *args, **kwargs)
        hub = Hub.current
        if hub.get_integration(StdlibIntegration) is None:
            return rv

        host = self.host
        port = self.port
        default_port = self.default_port

        real_url = url
        if not real_url.startswith(("http://", "https://")):
            real_url = "%s://%s%s%s" % (
                default_port == 443 and "https" or "http",
                host,
                port != default_port and ":%s" % port or "",
                url,
            )

        self._sentrysdk_data_dict = data = {}
        self._sentrysdk_span = hub.start_span(
            op="http", description="%s %s" % (real_url, method)
        )

        for key, value in hub.iter_trace_propagation_headers():
            self.putheader(key, value)

        data["url"] = real_url
        data["method"] = method
        return rv

    def getresponse(self, *args, **kwargs):
        rv = real_getresponse(self, *args, **kwargs)
        hub = Hub.current
        if hub.get_integration(StdlibIntegration) is None:
            return rv

        data = getattr(self, "_sentrysdk_data_dict", None) or {}

        if "status_code" not in data:
            data["status_code"] = rv.status
            data["reason"] = rv.reason

        span = self._sentrysdk_span
        if span is not None:
            span.set_tag("status_code", rv.status)
            for k, v in data.items():
                span.set_data(k, v)
            span.finish()

        hub.add_breadcrumb(
            type="http", category="httplib", data=data, hint={"httplib_response": rv}
        )
        return rv

    HTTPConnection.putrequest = putrequest
    HTTPConnection.getresponse = getresponse
