from ..Models.Cores.base_core import BaseLLM
from ..Prompts.prompt_template import PromptTemplate
from ..Embeddings.base_embeddings import BaseEmbeddingsToolkit
from .base_tool import BaseTool
from typing import Iterator, List, Dict, Any, Optional, Union, Literal, Type

WEB_SEARCH_TOOL_DESCRIPTION = """This tool searches the internet for facts or current information via a search engine.
Input of this tool is a search query. 
Output of this tool is the answer to your input question."""

QUERY_GENERATION_SYS_RPOMPT = """You are an AI assistant who is analysing the conversation you are having with the user. You shall use a search engine to find the most relevant information that can help you give the user the most accurate and coherent response. The user is asking you to generate the most appropriate search query for the latest user request.

Here are the most recent conversations you have had with the user:
"""

SEARCH_RESPONSE_SYS_RPOMPT = """You are a helpful AI assistant having a conversation with a user. You have just used a search engine to get some relevant information that might help you to respond to the user's latest request. Here are some relevant chunks of content that you found with the search engine. Use them to respond to the user if they are useful.

Relevant chunks of content:

"""

def ddg_search(query: str, n: int = 5, urls_only: bool = True, **kwargs) -> List[Union[str, Dict[str, Any]]]:
    """Search with DuckDuckGo.

    Args:
        query (str): Search query.
        n (int, optional): Maximum number of results. Defaults to 5.
        urls_only (bool, optional): Only return the list of urls or return other information as well. Defaults to True.

    Returns:
        List[Union[str, Dict[str, Any]]]: List of search results.
    """
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        results = [r for r in ddgs.text(query, max_results=n, **kwargs)]
    if urls_only:
        results = list(map(lambda x: x['href'], results))
    return results

def parse_url(url: str, timeout: int = 10) -> str:
    """Parse the given URL as markdown.

    Args:
        url (str): URL to parse.
        timeout (int, optional): Number of seconds before request time out. Defaults to 10.

    Returns:
        str: Content of the URL as markdown.
    """
    import requests
    from fake_useragent import UserAgent
    from markdownify import markdownify
    
    ua = UserAgent()
    response = requests.get(url, headers={'User-Agent': ua.random}, timeout=timeout)
    if response.status_code != 200:
        return ''
    else:
        content = response.text
        return markdownify(content, heading_style='ATX')
    
class WebSearchTool(BaseTool):
    """This is the tool class for doing web search.
    """
    def __init__(self, embeddings: Type[BaseEmbeddingsToolkit], 
                 name: str = 'web_search', description: str = WEB_SEARCH_TOOL_DESCRIPTION, 
                 search_engine: Literal['duckduckgo'] = 'duckduckgo', verbose: bool = True) -> None:
        """Initialise teh web search tool.

        Args:
            embeddings (Type[BaseEmbeddingsToolkit]): Embeddings to use for creating template
            name (str, optional): Name of the tool. Defaults to 'web_search'.
            description (str, optional): Description of the tool. Defaults to WEB_SEARCH_TOOL_DESCRIPTION.
            search_engine (Literal[&#39;duckduckgo&#39;], optional): Name of the search engine of the tool. Defaults to 'duckduckgo'.
            verbose: Whether to print logs while running the tool. Defaults to True.
        """
        super().__init__(name, description, verbose)
        from ..Data.vector_database import VectorDatabase
        self.search_engine = search_engine
        self.embeddings = embeddings
        self.vectordb = VectorDatabase.from_empty(embeddings=self.embeddings)

    def search(self, query: str, n: int = 5, urls_only: bool = True, **kwargs) -> List[Union[str, Dict[str, Any]]]:
        """Search with the given query.

        Args:
            query (str): Search query.
            n (int, optional): Maximum number of results. Defaults to 5.
            urls_only (bool, optional): Only return the list of urls or return other information as well. Defaults to True.

        Returns:
            List[Union[str, Dict[str, Any]]]: List of search results.
        """
        if self.search_engine == 'duckduckgo':
            return ddg_search(query=query, n=n, urls_only=urls_only, **kwargs)
        else:
            return [f'Search engine "{self.search_engine}" not supported.']
        

    def run(self, tool_input: str, llm: Optional[Type[BaseLLM]] = None, stream: bool = False, 
            history: Optional[List[List[str]]] = None, prompt_template: Optional[PromptTemplate] = None, 
            generate_query: bool = True, return_type: Literal['response', 'vectordb', 'chunks'] = 'response', **kwargs) -> Union[str, Iterator[str], List[Dict[str, Any]], Any]:
        """Run the web search tool. Any keyword arguments will be passed to the search method.

        Args:
            tool_input (str): Input of the tool, usually the latest user input in the chatbot conversation.
            llm (Optional[Type[BaseLLM]], optional): It will be used to create the search query and generate output if `generate_query=True`. 
            stream (bool, optional): If an llm is provided and `stream=True`, A generator of the output will be returned. Defaults to False.
            history (Optional[List[List[str]]], optional): Snippet of recent chat history to help forming more relevant search if provided. Defaults to None.
            prompt_template (Optional[PromptTemplate], optional): Prompt template use to format the chat history. Defaults to None.
            generate_query (bool, optional): Whether to treat the tool_input as part of the conversation and generate a different search query. Defaults to True.
            return_type (Literal['response', 'vectordb', 'chunks'], optional): Return a full response given the tool_input, the vector database, or the chunks only. Defaults to 'response'.

        Returns:
            Union[str, Iterator[str], List[Dict[str, Any]], Any]: Search result, if llm and prompt template is provided, the result will be provided as a reponse to the tool_input.
        """
        tool_input = tool_input.strip(' \n\r\t')
        if not generate_query:
            query = tool_input
        else:
            if ((history is not None) & (prompt_template is not None)):
                conversation = prompt_template.format_history(history=history) + prompt_template.human_prefix + tool_input
            elif prompt_template is not None:
                conversation = prompt_template.human_prefix + tool_input
            elif history is not None:
                raise ValueError('Prompt template need to be provided to process chat history.')
            else:
                conversation = 'User: ' + tool_input

            prompt_template = PromptTemplate.from_preset('Default Instruct') if prompt_template is None else prompt_template
            request = f'This is my latest request: {tool_input}\n\nGenerate the search query that helps you to search in the search engine and respond, in JSON format.'
            query_prompt = prompt_template.create_prompt(user=request, system=QUERY_GENERATION_SYS_RPOMPT + conversation)
            query_prompt += '```json\n{"Search query": "'
            query = '{"Search query": "' + llm(query_prompt, stop=['```'])
            try:
                import json
                query = json.loads(query)['Search query']
                self.print(f'Search query: {query}')
            except:
                self.print(f'Generation of query failed, fall back to use the raw tool_input "{tool_input}".')
                query = tool_input

        from ..TextSplitters.llm_text_splitter import LLMTextSplitter
        from ..Models.Cores.utils import add_newline_char_to_stopwords
        from .web_search_utils import get_markdown, create_content_chunks
        from langchain.schema.document import Document

        text_splitter = LLMTextSplitter(model=llm)
        results = self.search(query=query, urls_only=False, **kwargs)
        urls = list(map(lambda x: x['href'], results))
        if llm is None:
            contents = list(map(lambda x: get_markdown(x, as_list=False), urls))
            self.print('Parsing contents completed.')
            docs = list(map(lambda x: Document(page_content=x[0], metadata=x[1]), list(zip(contents, results))))
            docs = text_splitter.split_documents(documents=docs)
            index = list(map(lambda x: x.page_content, docs))
            data = list(map(lambda x: x.metadata, docs))
            self.print(f'Splitting contents completed. Number of documents: {len(index)}')
        else:
            contents = list(map(lambda x: get_markdown(x, as_list=True), urls))
            self.print('Parsing contents completed.')
            contents = list(map(lambda x: create_content_chunks(x, llm), contents))
            docs = list(zip(contents, results))
            docs = list(map(lambda x: list(map(lambda y: Document(page_content=y, metadata=x[1]), x[0])), docs))
            docs = sum(docs, [])
            index = list(map(lambda x: x.page_content, docs))
            data = list(map(lambda x: x.metadata, docs))
            self.print(f'Splitting contents completed. Number of documents: {len(index)}')
        self.vectordb.add_texts(texts=index, metadata=data, split_text=False)
        self.print('Storing contents completed.')

        if return_type == 'vectordb':
            return self.vectordb
        
        chunks = self.vectordb.search(query=query, top_k=3, index_only=False)
        if return_type == 'chunks':
            return chunks
        
        rel_info = list(map(lambda x: x['index'], chunks))
        rel_info = '\n\n'.join(rel_info) + '\n'

        prompt = prompt_template.create_prompt(user=tool_input, system=SEARCH_RESPONSE_SYS_RPOMPT + rel_info, history=history if history is not None else [])
        stop = add_newline_char_to_stopwords(prompt_template.stop)
        if stream:
            return llm.stream(prompt, stop=stop)
        else:
            return llm(prompt, stop=stop)
        


            



