# -*- coding: utf-8 -*-
import time
import os
import importlib.util as importer

import flask
from flask import Request, Response
from flask_http_middleware import BaseHTTPMiddleware

###########################
# opentelemetry 
###########################
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry import trace

OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
#SERVICE_APP_NAME = os.environ.get("SERVICE_APP_NAME", "app")
SERVICE_APP_NAME = os.environ.get('SERVICE_APP_NAME')
HTTP_500_INTERNAL_SERVER_ERROR = 500

###########################
# opentelemetry metrics
###########################
from prometheus_client import start_http_server
from opentelemetry import metrics
from opentelemetry.metrics import (
    CallbackOptions,
    Observation,
)

from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader, 
    ConsoleMetricExporter
)

# Start Prometheus client
start_http_server(port=8000, addr="0.0.0.0")
otel_metrics_prometheus_reader = PrometheusMetricReader()

otel_metrics_provider = MeterProvider(
    resource=Resource.create(attributes={
        #SERVICE_NAME: SERVICE_APP_NAME,
        "service.name" : SERVICE_APP_NAME,
        "service.namespace": SERVICE_APP_NAME,
        "service.instance.id": SERVICE_APP_NAME,
        "compose_service": SERVICE_APP_NAME,
        
    }),
    metric_readers=[otel_metrics_prometheus_reader],
)
set_meter_provider(otel_metrics_provider)
otel_metrics_meter = otel_metrics_provider.get_meter(SERVICE_APP_NAME, True)

INFO = otel_metrics_meter.create_counter(
    name="flaskapi_app_info",
    description="FlaskAPI application information",
)

# Create OpenTelemetry Meter
REQUESTS = otel_metrics_meter.create_counter(
    name="flaskapi_requests_total",
    description="Total count of requests",
)

RESPONSES = otel_metrics_meter.create_counter(
    name="flaskapi_responses_total",
    description="Total count of requests",
)

REQUESTS_PROCESSING_TIME = otel_metrics_meter.create_histogram(
    name="flaskapi_requests_duration_seconds",
    description="measures the duration of the inbound request",
)

EXCEPTIONS = otel_metrics_meter.create_counter(
    name="flaskapi_exceptions_total",
    description="Total count of exceptions",
)

REQUESTS_IN_PROGRESS = otel_metrics_meter.create_up_down_counter(
    name="flaskapi_requests_in_progress",
    description="Gauge of requests by method and path currently being processed",
)

###########################
# opentelemetry traces
###########################
from grpc import Compression
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor

otlp_trace_exporter = OTLPSpanExporter(
    endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT'), 
    compression=Compression.Gzip)

span_otel_processor = BatchSpanProcessor(otlp_trace_exporter)
tracer_provider = TracerProvider(
    resource=Resource.create(attributes={
        "service.name" : SERVICE_APP_NAME,
        "service.namespace": SERVICE_APP_NAME,
        "service.instance.id": SERVICE_APP_NAME,
        "compose_service": SERVICE_APP_NAME,
    })
)
tracer_provider.add_span_processor(span_otel_processor)
trace.set_tracer_provider(tracer_provider)


###########################
# opentelemetry logs
###########################
import logging
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter

logger_provider = LoggerProvider(
    resource=Resource.create({
        #SERVICE_NAME: SERVICE_APP_NAME,
        "service.name" : SERVICE_APP_NAME,
        "service.namespace": SERVICE_APP_NAME,
        "service.instance.id": SERVICE_APP_NAME,
        "compose_service": SERVICE_APP_NAME,
        }),
)
set_logger_provider(logger_provider)
otel_logger_exporter = OTLPLogExporter(
    endpoint=OTEL_EXPORTER_OTLP_ENDPOINT, 
    insecure=True)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(otel_logger_exporter))
logger_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
# Attach OTLP handler to root logger
logging.getLogger().addHandler(logger_handler)

# LoggingInstrumentor
LoggingInstrumentor().instrument(
    set_logging_format=True,
    logging_format="%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s] - %(message)s",
    #log_level=logging.ERROR
    log_level=logging.INFO
)

###########################
# opentelemetry requests
###########################
from opentelemetry.instrumentation.requests import RequestsInstrumentor
RequestsInstrumentor().instrument()


###########################
# MetricsMiddleware 
###########################
class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self):
        super().__init__()
        #self.app_name = os.environ.get("SERVICE_NAME", "app")
        self.app_name = SERVICE_APP_NAME
        INFO.add(amount=1, attributes={
            "app_name":self.app_name
        })

    def dispatch(self, request, call_next):
        method = request.method
        path = request.path
        
        REQUESTS_IN_PROGRESS.add(amount=1, attributes={
            "method":method, 
            "path":path, 
            "app_name":self.app_name
        })
        REQUESTS.add(amount=1, attributes ={
            "method":method, 
            "path":path, 
            "app_name":self.app_name
        })

        before_time = time.perf_counter()
        try:
            response = call_next(request)
        except BaseException as e:
            status_code = HTTP_500_INTERNAL_SERVER_ERROR
            EXCEPTIONS.add(amount=1, attributes={
                "method":method, 
                "path":path, 
                "exception_type": type(e).__name__,
                "app_name":self.app_name
            })
            raise e from None
        else:
            status_code = response.status_code
            total_request_time = time.perf_counter() - before_time
            span = trace.get_current_span()
            trace_id = trace.format_trace_id(
                span.get_span_context().trace_id)

            REQUESTS_PROCESSING_TIME.record(total_request_time, attributes={
                "method":method, 
                "path":path, 
                "app_name":self.app_name,
                #"trace_id": trace_id
                #'TraceID': trace_id
                #"exemplar":{'TraceID': trace_id}
            })
        finally:
            RESPONSES.add(amount=1, attributes={
                "method": method, 
                "path": path, 
                "app_name": self.app_name,
                "status_code": status_code
            })
            REQUESTS_IN_PROGRESS.add(amount=-1, attributes={
                "method":method, 
                "path":path, 
                "app_name":self.app_name
            })
        return response

def otel_instrument_app(app: flask.Flask):
    FlaskInstrumentor().instrument_app(
        app,
        tracer_provider=tracer_provider)

    #if importer.find_spec('opentelemetry.instrumentation.flask'):
    #    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    #    flask_instrumentor = FlaskInstrumentor()
    #    if not flask_instrumentor.is_instrumented_by_opentelemetry:
    #        flask_instrumentor.instrument_app(app)


from flask import Request, Response
from prometheus_client import REGISTRY
from prometheus_client.openmetrics.exposition import (CONTENT_TYPE_LATEST,
                                                      generate_latest)
def metrics():
    '''Returns the metrics from the registry in latest text format as a string.'''
    return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})

