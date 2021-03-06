import json
from .Exceptions import (
        JsonRPCError,
        ParseError,
        InvalidRequestError,
        NotFoundError,
        InvalidParamsError,
        InternalError,
        UnimplementedError,
        exceptions_from_codes)
from .custom_json import from_json,to_json

class JsonRPCABC():
    '''Abstract Base Class defining generic functions relating to JSON-RPC 2.0.
    The referenced specification is available here:
    http://www.jsonrpc.org/specification.'''


    _id = 0

    def request(self, method_name:str, *, id_num=None, positional_params=None,
            keyword_params:dict=None, notification=False):
        '''create a json request object out of the specified arguments
        provided.'''

        request_dict = {
                'jsonrpc' : '2.0',
                'method'  : method_name}

        id_to_use = None
        if not notification:
            if id_num is not None:
                id_to_use = id_num
            else:
                id_to_use = self._id
                self._id += 1
            request_dict['id'] = id_to_use

        #grab the first non empty argument and default to None otherwise
        params_to_use = next(
            (_ for _ in (positional_params, keyword_params) if _), None)

        if params_to_use:
            request_dict['params'] = params_to_use

        return json.dumps(request_dict, default=to_json), id_to_use

    @staticmethod
    def response_result(id_num:int, result):
        '''create an result response object based on the given arguments
        Args:
            id_num (int): the id of the response
            result : some form of object that is parsable into json format

        Returns:
            str: A json formatted string'''

        response_dict = {
                'jsonrpc' : '2.0',
                'result'  : result,
                'id'      : id_num
                        }
        return json.dumps(response_dict, default=to_json)

    @staticmethod
    def response_error(exception, id_num='null'):
        '''create an error response object based on the given arguments
        Args:
            exception (JsonRPCError): an exception with the necessary
            information to generate a JSON error response object

        Returns:
            str: A json formatted string'''

        response_dict = {
                'jsonrpc' : '2.0',
                'error'   : exception.to_json_rpc_dict(),
                'id'      : id_num
                        }
        return json.dumps(response_dict, default=to_json)

    async def process_request(self, request):
        '''Received JSON indicates a request object. A server would need to
        cater for this function. A client wouldn't need to implement this.
        There is a possibility that an implementation of this class could
        operate as a peer in which case it would make sense to implement this
        function when implementing a client.

        Args:
            request (dict): a dictionary containing the request to service

        Returns:
            response_object: the pre-jsonified response
        '''

        raise UnimplementedError()

    async def process_notification(self, notification):
        '''Process a notification object. Similar to a request but don't respond
        with anything
        Args:
            notification (a json object):the decoded notification from the
            client
        '''

    def process_response(self, response):
        '''Received JSON indicates a response object. A server would not need to
        cater for this function. A client would need to implement this.
        There is a possibility that an implementation of this class could
        operate as a peer in which case it would make sense to implement this
        function when implementing a server'''

        raise UnimplementedError()

    def process_error(self, json_dict:dict):
        raise UnimplementedError()

    def exception_from_json_dict(self, json_dict:dict)->Exception:
        '''create an exception from a json error dict'''
        #first get error_dict
        code = json_dict.get('code')
        data = json_dict.get('data')
        if data is not None:
            details = data.get('details')
        else:
            details = ''
        
        if code is not None:
            exc = exceptions_from_codes[code](details)
        else:
            exc = JsonRPCError(details)
        return exc

    async def process_incoming(self, json_obj:str) -> str:
        '''Process an incoming (either to a client or server) string. This
        function is always expected to return some form of string which can be
        sent to the sender in a jsonified string.'''

        try:
            result = json.loads(json_obj, object_hook=from_json)
        except ValueError as e:
            p = ParseError(e.__str__())
            return self.response_error(p), p

        #now parse it for legitimacy
        if type(result) == list:
            if len(result) == 0:
                i = InvalidRequestError('Sent an empty batch')
                return self.response_error(i), i
            else:
                #process a batch
                raise UnimplementedError('Fixme - handle a batch!')

        if ('jsonrpc','2.0') not in result.items():
            i = InvalidRequestError('Missing or invalid rpc spec information')
            return self.response_error(i), i

        if 'method' in result:
            method_arg = result['method']
            #it's a request
            if 'id' not in result: #it's a notification
                return await self.process_notification(result)
            id_num = result['id']
            if type(id_num) != int:
                i = InvalidRequestError( 'id in request must be an integer')
                return self.response_error(i), i
            if type(method_arg) == int:
                i = InvalidRequestError( 'method cannot be a number')
                return self.response_error(i, id_num=id_num), i
            if type(method_arg) != str:
                i = InvalidRequestError( 'method name has to be a string')
                return self.response_error(i, id_num=id_num), i
            if len(method_arg) == 0:
                i = InvalidRequestError( 'method cannot be empty')
                return self.response_error(i, id_num=id_num), i
            if method_arg[:1].isdigit():
                i = InvalidRequestError( 'method cannot start with a number')
                return self.response_error(i, id_num=id_num), i
            else:
                return await self.process_request(result)
        elif 'result' in result:
            if 'id' not in result:
                i = InvalidRequestError('Missing ID in result')
                return self.response_error(i), i
            if 'error' in result:
                i = InvalidRequestError(
                        'Result contains a result and an error field')
                return self.response_error(i), i

            return self.process_response(result)
        elif 'error' in result:
            return self.process_error(result)


