"""
PyWorker works as a man-in-the-middle between the client and model API. It's function is:
1. receive request from client, update metrics such as workload of a request, number of pending requests, etc.
2a. transform the data and forward the transformed data to model API
2b. send updated metrics to autoscaler
3. transform response from model API(if needed) and forward the response to client

PyWorker forward requests to many model API endpoint. each endpoint must have an EndpointHandler. You can also
write function to just forward requests that don't generate anything with the model to model API without an
EndpointHandler. This is useful for endpoints such as healthchecks. See below for example
"""

import os
import logging
import dataclasses
from typing import Dict, Any, Optional, Union, Type

from aiohttp import web, ClientResponse

from lib.backend import Backend, LogAction
from lib.data_types import EndpointHandler
from lib.server import start_server
from .data_types import TTSRequest


# the url and port of model API
MODEL_SERVER_URL = "http://0.0.0.0:5001"

# This is the log line that is emitted once the server has started
MODEL_SERVER_START_LOG_MSG = "infer server has started"
MODEL_SERVER_ERROR_LOG_MSGS = [
    "Exception: corrupted model file"  # message in the logs indicating the unrecoverable error
]


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s[%(levelname)-5s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__file__)


# This class is the implementer for the '/generate' endpoint of model API
@dataclasses.dataclass
class TTSHandler(EndpointHandler[TTSRequest]):

    @property
    def endpoint(self) -> str:
        # API endpoint
        return "/generate"
    
    @property
    def healthcheck_endpoint(self) -> str:
        # 모델 서버에서 healthcheck endpoint를 제공하지 않았다면, pyworker에서 사용 X
        return None    

    @classmethod
    def payload_cls(cls) -> Type[TTSRequest]:
        return TTSRequest # 사용하는 payload의 class 알려줌 
    

    def generate_payload_json(self, payload: TTSRequest) -> Dict[str, Any]:
        """
        defines how to convert `TTSRequest` defined above, to
        JSON data to be sent to the model API. This function too is a simple dataclass -> JSON, but
        can be more complicated, See comfyui for an example
        PyWorker가 모델 API에 보낼 JSON 데이터를 만들기 위한 로직
        """
        return dataclasses.asdict(payload)
    
    def make_benchmark_payload(self) -> TTSRequest:
        """
        defines how to generate an InputData for benchmarking. This needs to be defined in only
        one EndpointHandler, the one passed to the backend as the benchmark handler
         모델 서버가 잘 작동하는지 확인하거나,
        ▶️ 부하 테스트(로드 테스트)를 위해,
        ▶️ 미리 정의된 더미 입력 데이터를 생성
        """
        return TTSRequest.for_test()

    async def generate_client_response(
        self, client_request: web.Request, model_response: ClientResponse
    ) -> Union[web.Response, web.StreamResponse]:
        """
        defines how to convert a model API response to a response to PyWorker client
        """
        _ = client_request
        match model_response.status:
            case 200:
                log.debug("SUCCESS")
                data = await model_response.json()
                return web.json_response(data=data)
            case code:
                log.debug("SENDING RESPONSE: ERROR: unknown code")
                return web.Response(status=code)


backend = Backend(
    model_server_url=MODEL_SERVER_URL,
    # location of model log file
    model_log_file=os.environ["MODEL_LOG"],
    # for some model backends that can only handle one request at a time, be sure to set this to False to
    # let PyWorker handling queueing requests.
    allow_parallel_requests=True,
    # give the backend an EndpointHandler instance that is used for benchmarking
    # number of benchmark run and number of words for a random benchmark run are given
    benchmark_handler=TTSHandler(benchmark_runs=3),
    # defines how to handle specific log messages. See docstring of LogAction for details
    log_actions=[
        (LogAction.ModelLoaded, MODEL_SERVER_START_LOG_MSG),
        (LogAction.Info, '"message":"Download'),
        *[
            (LogAction.ModelError, error_msg)
            for error_msg in MODEL_SERVER_ERROR_LOG_MSGS
        ],
    ],
)


# this is a simple ping handler for pyworker
# PyWorker 서버가 정상적으로 작동 중인지 간단히 확인
async def handle_ping(_: web.Request):
    return web.Response(body="pong")


# this is a handler for forwarding a health check to modelAPI
async def handle_healthcheck(_: web.Request):
    healthcheck_res = await backend.session.get("/healthcheck")
    return web.Response(body=healthcheck_res.content, status=healthcheck_res.status)

routes = [
    web.post("/generate", backend.create_handler(TTSHandler())),
    web.get("/ping", handle_ping),
    web.get("/healthcheck", handle_healthcheck),
]

if __name__ == "__main__":
    start_server(backend, routes)