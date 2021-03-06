import pytest
import json
from aio_rpc.Exceptions import (NotFoundError,
                                InvalidParamsError,
                                InternalError,
                                InvalidRequestError)
from aio_rpc.JsonRPCABC import JsonRPCABC

@pytest.mark.asyncio
async def test_call(srv):
    result = await srv.obj.add(1,2)
    assert result == 3

    req, id_num = srv.request('add', positional_params = [2,2])

    result_json,e = await srv.process_incoming(req)
    result = json.loads(result_json)
    assert result['result'] == 4

@pytest.mark.asyncio
async def test_call_bad(srv):

    req, id_num = srv.request('non_existant_func', positional_params = [2,2], id_num=8)

    result_json, error = await srv.process_incoming(req)
    e = NotFoundError("'<class 'aio_rpc.Wrapper.Wrapper'>' object has no"
           " attribute 'non_existant_func'")
    expected_result = srv.response_error(e, id_num = id_num)


    assert expected_result == result_json

@pytest.mark.asyncio
async def test_call_bad_args(srv):
    req, id_num = srv.request('add', positional_params = [2,2,2], id_num=9)

    result_json,error = await srv.process_incoming(req)
    e = InvalidParamsError("too many positional arguments")
    expected_result = srv.response_error(e, id_num = id_num)

    assert expected_result == result_json

@pytest.mark.asyncio
async def test_call_empty_method(srv):
    req, id_num = srv.request('add', positional_params = [2,2,2], id_num=9)
    req_dict = json.loads(req)
    req_dict['method'] = ''
    req = json.dumps(req_dict)

    result_json,error = await srv.process_incoming(req)
    e = InvalidRequestError("method cannot be empty")
    expected_result = srv.response_error(e, id_num = id_num)

    assert expected_result == result_json

@pytest.mark.asyncio
async def test_call_internal_error(srv):
    req, id_num = srv.request('raise_exception', id_num=10)

    result_json,error = await srv.process_incoming(req)
    result_dict = json.loads(result_json)
    #print(result_dict)
    e = InternalError("division by zero")
    expected_result = srv.response_error(e, id_num = id_num)

    assert expected_result == result_json

