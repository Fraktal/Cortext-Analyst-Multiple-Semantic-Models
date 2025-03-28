import requests
import json
import os
from generate_jwt import JWTGenerator

DEBUG = False


class CortexChat:
    def __init__(self,
                 agent_url: str,
                 search_services: list,
                 semantic_models: list,
                 model: str,
                 account: str,
                 user: str,
                 private_key_path: str
                 ):
        self.agent_url = agent_url
        self.model = model
        self.search_services = search_services
        self.semantic_models = semantic_models
        self.account = account
        self.user = user
        self.private_key_path = private_key_path
        self.jwt = self._generate_jwt()

    def _generate_jwt(self):
        return JWTGenerator(self.account, self.user, self.private_key_path).get_token()

    def _retrieve_response(self, query: str, limit=1) -> dict[str, any]:
        url = self.agent_url
        headers = {
            'X-Snowflake-Authorization-Token-Type': 'KEYPAIR_JWT',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f"Bearer {self.jwt}"
        }

        # Set up tools and tool resources
        tools = []
        tool_resources = {}

        # Add multiple search services
        for i, search_service in enumerate(self.search_services):
            search_tool_name = f"search_service_{i}"
            tools.append({
                "tool_spec": {
                    "type": "cortex_search",
                    "name": search_tool_name
                }
            })

            tool_resources[search_tool_name] = {
                "name": search_service,
                "max_results": limit,
                "title_column": "title",
                "id_column": "relative_path",
            }

        # Add multiple text-to-SQL tools and their resources
        for i, semantic_model in enumerate(self.semantic_models):
            tool_name = f"semantic_model_{i}"
            tools.append({
                "tool_spec": {
                    "type": "cortex_analyst_text_to_sql",
                    "name": tool_name
                }
            })

            # Handle different formats of semantic model paths
            # Snowflake stage path format (@DB.SCHEMA.STAGE/file.yaml)
            if semantic_model.startswith('@') and '/' in semantic_model:
                # This is already in the correct format for stage files
                tool_resources[tool_name] = {
                    "semantic_model_file": semantic_model
                }
            # Regular Snowflake identifier (@DB.SCHEMA.MODEL or DB.SCHEMA.MODEL)
            elif semantic_model.startswith('@') or '.' in semantic_model:
                # Remove @ if present
                model_path = semantic_model.lstrip('@')
                tool_resources[tool_name] = {
                    "semantic_model": model_path
                }
            # Local file path
            else:
                tool_resources[tool_name] = {
                    "semantic_model_file": semantic_model
                }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": query
                        }
                    ]
                }
            ],
            "tools": tools,
            "tool_resources": tool_resources,
        }

        # Debug log the entire request data
        if DEBUG:
            print("Request data:")
            print(json.dumps(data, indent=2))
            print("\nRequest headers:")
            for key, value in headers.items():
                print(f"{key}: {'*****' if key == 'Authorization' else value}")

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 401:  # Unauthorized - likely expired JWT
            print("JWT has expired. Generating new JWT...")
            # Generate new token
            self.jwt = self._generate_jwt()
            # Retry the request with the new token
            headers["Authorization"] = f"Bearer {self.jwt}"
            print("New JWT generated. Sending new request to Cortex Agents API. Please wait...")
            response = requests.post(url, headers=headers, json=data)

        if DEBUG:
            print(response.text)

        if response.status_code == 200:
            return self._parse_response(response)
        else:
            print(f"Error: Received status code {response.status_code}")
            print(f"Response content: {response.text}")
            # Return a structured error response
            return {
                "text": f"Error {response.status_code}: {response.text}",
                "sql": "",
                "sql_results": {},
                "search_results": {},
                "citations": ""
            }

    def _parse_delta_content(self, content: list) -> dict[str, any]:
        """Parse different types of content from the delta."""
        result = {
            'text': '',
            'tool_use': [],
            'tool_results': []
        }

        for entry in content:
            entry_type = entry.get('type')
            if entry_type == 'text':
                result['text'] += entry.get('text', '')
            elif entry_type == 'tool_use':
                result['tool_use'].append(entry.get('tool_use', {}))
            elif entry_type == 'tool_results':
                result['tool_results'].append(entry.get('tool_results', {}))

        return result

    def _process_sse_line(self, line: str) -> dict[str, any]:
        """Process a single SSE line and return parsed content."""
        if not line.startswith('data: '):
            return {}
        try:
            json_str = line[6:].strip()  # Remove 'data: ' prefix
            if json_str == '[DONE]':
                return {'type': 'done'}

            data = json.loads(json_str)
            if data.get('object') == 'message.delta':
                delta = data.get('delta', {})
                if 'content' in delta:
                    return {
                        'type': 'message',
                        'content': self._parse_delta_content(delta['content'])
                    }
            return {'type': 'other', 'data': data}
        except json.JSONDecodeError:
            return {'type': 'error', 'message': f'Failed to parse: {line}'}

    def _parse_response(self, response: requests.Response) -> dict[str, any]:
        """Parse and print the SSE chat response with improved organization."""
        accumulated = {
            'text': '',
            'tool_use': [],
            'tool_results': [],
            'other': []
        }

        for line in response.iter_lines():
            if line:
                result = self._process_sse_line(line.decode('utf-8'))

                if result.get('type') == 'message':
                    content = result['content']
                    accumulated['text'] += content['text']
                    accumulated['tool_use'].extend(content['tool_use'])
                    accumulated['tool_results'].extend(content['tool_results'])
                elif result.get('type') == 'other':
                    accumulated['other'].append(result['data'])

        text = ''
        sql = ''  # For backward compatibility
        sql_results = {}  # Dict to store results from multiple semantic models
        search_results = {}  # Dict to store results from multiple search services
        citations = ''

        if accumulated['text']:
            text = accumulated['text']

        if DEBUG:
            print("\n=== Complete Response ===")

            print("\n--- Generated Text ---")
            print(text)

            if accumulated['tool_use']:
                print("\n--- Tool Usage ---")
                print(json.dumps(accumulated['tool_use'], indent=2))

            if accumulated['other']:
                print("\n--- Other Messages ---")
                print(json.dumps(accumulated['other'], indent=2))

            if accumulated['tool_results']:
                print("\n--- Tool Results ---")
                print(json.dumps(accumulated['tool_results'], indent=2))

        if accumulated['tool_results']:
            for result in accumulated['tool_results']:
                for k, v in result.items():
                    if k == 'content':
                        for content in v:
                            if 'sql' in content['json']:
                                # Extract the tool name to identify which semantic model was used
                                tool_name = result.get('tool_call_id', '').split(':')[-1]
                                sql_results[tool_name] = content['json']['sql']
                                # For backward compatibility, also store the first SQL result in the sql field
                                if not sql:
                                    sql = content['json']['sql']
                            elif 'searchResults' in content['json']:
                                # Extract the tool name to identify which search service was used
                                tool_name = result.get('tool_call_id', '').split(':')[-1]
                                result_items = content['json']['searchResults']

                                # Store the search results by tool name
                                search_results[tool_name] = result_items

                                # Process citations
                                for search_result in result_items:
                                    citations += f"{search_result['text']}"
                                text = text.replace("【†1†】", "").replace("【†2†】", "").replace("【†3†】", "").replace(" .",
                                                                                                                   ".") + "*"
                                citations = f"{search_result['doc_title']} \n {citations} \n\n[Source: {search_result['doc_id']}]"

        # Ensure all expected keys are present (with defaults)
        return {
            "text": text,
            "sql": sql,
            "sql_results": sql_results,
            "search_results": search_results,
            "citations": citations if citations else ""
        }

    def chat(self, query: str) -> any:
        response = self._retrieve_response(query)
        return response