from ..Cores.base_core import BaseCore, BaseLLM
from ...Prompts.prompt_template import PromptTemplate
from typing import Literal, Optional, Dict, List, Any, Type

def detect_model_type(model_id: str) -> str:
    """This function attempts to get the model format type with the model id.

    Args:
        model_id (str): Model ID form Huggingface.

    Returns:
        str: Model format type.
    """
    model_id = model_id.lower()
    if 'gguf' in model_id:
        return 'gguf'
    elif 'awq' in model_id:
        return 'awq'
    elif 'gptq' in model_id:
        return 'gptq'
    else:
        return 'default'

class LlmFactory:

    def __init__(self, model_id: str, model_type: Literal['auto', 'default', 'gptq', 'awq', 'gguf', 'openai', 'debug'] = 'auto', **kwargs) -> None:
        """Initiate the model core to create LLMs.

        Args:
            model_id (str): Model id (from Huggingface) to use.
            model_type (Literal[&#39;auto&#39;, &#39;default&#39;, &#39;gptq&#39;, &#39;awq&#39;, &#39;gguf&#39;, &#39;openai&#39;, &#39;debug&#39;], optional): Type of model format, if 'auto' is given, model_type will be automatically detected. Defaults to 'auto'.
        """
        self._model_id = model_id
        self._model_type = detect_model_type(model_id=model_id) if model_type=='auto' else model_type
        if self.model_type == 'gguf':
            from ..Cores.llamacpp_core import LlamaCppCore
            self._core = LlamaCppCore(self.model_id, **kwargs)
        elif self.model_type in ['default', 'awq', 'gptq']:
            from ..Cores.huggingface_core import HuggingfaceCore
            self._core = HuggingfaceCore(self.model_id, model_type=self.model_type, **kwargs)
        elif self.model_type == 'openai':
            from ..Cores.openai_core import OpenAICore
            api_key = kwargs.get('api_key', None)
            base_url = kwargs.get('base_url', None)
            tokenizer_id = kwargs.get('tokenizer_id', None)
            tokenizer_kwargs = kwargs.get('tokenizer_kwargs', dict())
            self._core = OpenAICore(base_url=base_url, api_key=api_key, model_id=model_id, tokenizer_id=tokenizer_id, tokenizer_kwargs=tokenizer_kwargs)
            self._model_id = self.core.model_id
        elif self.model_type == 'debug':
            self._core = BaseCore(model_id=self.model_id, **kwargs)
        else:
            raise ValueError(f'Model type "{self.model_type}" not supported.')
        

    @property
    def model_id(self) -> str:
        """Model id (from Huggingface).

        Returns:
            str: Model id (from Huggingface).
        """
        return self._model_id
    
    @property
    def model_type(self) -> str:
        """Type of model format.

        Returns:
            str: Type of model format.
        """
        return self._model_type 
    
    @property
    def core(self) -> Type[BaseCore]:
        """Core model of the llm factory.

        Returns:
            Type[BaseCore]: Core model of the llm factory.
        """
        return self._core
    
    @property
    def prompt_template(self) -> PromptTemplate:
        """Default prompt template for the model.

        Returns:
            PromptTemplate: Default prompt template for the model.
        """
        return self.core.prompt_template
    
    def __call__(self, temperature: float = 0.8, max_new_tokens: int = 2048, top_p: float = 0.95,
                top_k: int = 40, repetition_penalty: float = 1.1, stop: Optional[List[str]] = None, 
                newline=True, **kwargs: Dict[str, Any]) -> BaseLLM:
        """Calling the object will create a langchain format llm with the generation configurations passed from the arguments. 

        Args:
            temperature (float, optional): Set how "creative" the model is, the samller it is, the more static of the output. Defaults to 0.8.
            max_new_tokens (int, optional): Maximum number of tokens to generate by the llm. Defaults to 2048.
            top_p (float, optional): While sampling the next token, only consider the tokens above this p value. Defaults to 0.95.
            top_k (int, optional): While sampling the next token, only consider the top "top_k" tokens. Defaults to 40.
            repetition_penalty (float, optional): The value to penalise the model for generating repetitive text. Defaults to 1.1.
            stop (Optional[List[str]], optional): List of strings to stop the generation of the llm. Defaults to None.
            newline (bool, optional): Whether to add a newline character to the beginning of the "stop" list provided. Defaults to True.

        Returns:
            Type[BaseLLM]: An LLM.
        """
        return self.call(temperature=temperature, max_new_tokens=max_new_tokens,
                          top_p=top_p, top_k=top_k, repetition_penalty=repetition_penalty,
                          stop=stop, newline=newline, **kwargs)
    
    def call(self, temperature: float = 0.8, max_new_tokens: int = 2048, top_p: float = 0.95,
                top_k: int = 40, repetition_penalty: float = 1.1, stop: Optional[List[str]] = None, 
                newline=True, **kwargs: Dict[str, Any]) -> Type[BaseLLM]:
        """Calling the object will create a langchain format llm with the generation configurations passed from the arguments. 

        Args:
            temperature (float, optional): Set how "creative" the model is, the samller it is, the more static of the output. Defaults to 0.8.
            max_new_tokens (int, optional): Maximum number of tokens to generate by the llm. Defaults to 2048.
            top_p (float, optional): While sampling the next token, only consider the tokens above this p value. Defaults to 0.95.
            top_k (int, optional): While sampling the next token, only consider the top "top_k" tokens. Defaults to 40.
            repetition_penalty (float, optional): The value to penalise the model for generating repetitive text. Defaults to 1.1.
            stop (Optional[List[str]], optional): List of strings to stop the generation of the llm. Defaults to None.
            newline (bool, optional): Whether to add a newline character to the beginning of the "stop" list provided. Defaults to True.

        Returns:
            BaseLLM: An LLM.
        """
        if self.model_type == 'gguf':
            from ..Cores.llamacpp_core import LlamaCppLLM
            return LlamaCppLLM(core=self.core, temperature=temperature, max_new_tokens=max_new_tokens, 
                                 top_p=top_p, top_k=top_k, repetition_penalty=repetition_penalty, stop=stop, stop_newline_version=newline)
        elif self.model_type in ['default', 'awq', 'gptq']:
            from ..Cores.huggingface_core import HuggingfaceLLM
            return HuggingfaceLLM(core=self.core, temperature=temperature, max_new_tokens=max_new_tokens, 
                                 top_p=top_p, top_k=top_k, repetition_penalty=repetition_penalty, stop=stop, stop_newline_version=newline)
        elif self.model_type == 'openai':
            from ..Cores.openai_core import OpenAILLM
            return OpenAILLM(core=self.core, temperature=temperature, max_new_tokens=max_new_tokens, 
                                 top_p=top_p, top_k=top_k, repetition_penalty=repetition_penalty, stop=stop, stop_newline_version=newline)
        elif self.model_type =='debug':
            from ..Cores.base_core import DebugLLM
            return DebugLLM(core=self.core, temperature=temperature, max_new_tokens=max_new_tokens, 
                                 top_p=top_p, top_k=top_k, repetition_penalty=repetition_penalty, stop=stop, stop_newline_version=newline)
        else:
            raise ValueError(f'Model type "{self.model_type}" not supported.')
