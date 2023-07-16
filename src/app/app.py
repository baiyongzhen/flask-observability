#!/usr/bin/env python3.8
# -*- coding: utf-8 -*-
import json
import logging
import os
import random
import time

from flask import Flask
from flask_http_middleware import MiddlewareManager
from tracing import otel_instrument_app, metrics

import tracing
from tracing import MetricsMiddleware

import requests
#from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.propagate import inject
TARGET_ONE_HOST = os.environ.get("TARGET_ONE_HOST", "app-b")
TARGET_TWO_HOST = os.environ.get("TARGET_TWO_HOST", "app-c")

app = Flask(__name__)
app.wsgi_app = MiddlewareManager(app)
app.wsgi_app.add_middleware(MetricsMiddleware)
otel_instrument_app(app)

@app.get("/health")
def health():
    return {"message":"I'm healthy"}

@app.get("/")
def read_root():
    logging.info("Hello World")
    return {"Hello": "World"}

@app.get("/io_task")
def io_task():
    time.sleep(1)
    logging.error("io task")
    return "IO bound task finish!"

@app.get("/cpu_task")
def cpu_task():
    for i in range(1000):
        n = i*i*i
    #logging.error("cpu task")
    logging.info("cpu task")
    return "CPU bound task finish!"

@app.get("/random_status")
def random_status():
    logging.error("random status")
    return {"path": "/random_status"}

@app.get("/random_sleep")
def random_sleep():
    time.sleep(random.randint(0, 5))
    #logging.error("random sleep")
    logging.info("random sleep")
    return {"path": "/random_sleep"}

@app.get("/error_test")
def error_test():
    logging.error("got error!!!!")
    raise ValueError("value error")


@app.route("/chain")
def chain():
    headers = {}
    inject(headers)  # inject trace info to header
    logging.critical(headers)

    with open('./data.json','w') as f:
        json.dump(headers, f, ensure_ascii=False, indent=4)

    response = requests.get(url=f"http://localhost:5000/", headers=headers)
    logging.info(response.content)
    response = requests.get(url=f"http://{TARGET_ONE_HOST}:5000/io_task", headers=headers)
    logging.info(response.content)
    response = requests.get(url=f"http://{TARGET_TWO_HOST}:5000/cpu_task", headers=headers)
    logging.info(response.content)        
    
    logging.info("Chain Finished")
    return {"path": "/chain"}


if __name__ == "__main__":
   app.run(debug=True)
