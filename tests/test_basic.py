from asyncio import TimeoutError
import pytest
import time

def test_basic(rpc):
    t1 = time.time()
    rpc.loop.run_until_complete(rpc.funcs['block_10ms']())
    t2 = time.time()
    print("Delta = {} seconds".format(t2-t1))

def test_except(rpc):
    with pytest.raises(TimeoutError):
        rpc.loop.run_until_complete(rpc.funcs['block'](2))
