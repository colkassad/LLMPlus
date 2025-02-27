import os
from transformers import StoppingCriteria, StoppingCriteriaList
from langchain.callbacks.manager import CallbackManagerForLLMRun
from .base_core import BaseCore, BaseLLM
from typing import Optional, List, Dict, Any, Union, Iterator, Literal

class KeywordsStoppingCriteria(StoppingCriteria):
    '''class for handling stop words in transformers.pipeline'''
    def __init__(self, stop_words: List[str], tokenizer: Any) -> None:
        self.tokenizer = tokenizer
        self.stopwords = stop_words
        self.stop_ids = list(map(lambda x: self.get_min_ids(x), stop_words))

    def __call__(self, input_ids: Any, scores: Any, **kwargs) -> bool:
        input_list = input_ids[0].tolist()
        for i in self.stop_ids:
            last = len(i)
            if len(input_list) >= last:
                comp = input_list[-last:]
                if comp==i:
                    return True
        return False
    
    def get_min_ids(self, word: str) -> List[int]:
        ids = self.tokenizer.encode(word, add_special_tokens=False)
        effective = list()
        for i in range(len(ids)):
            temp = ids[i:]
            text = self.tokenizer.decode(temp)
            if text==word:
                effective.append((text, temp))
            else:
                break
        for i in range(len(ids)):
            temp = ids[:-i]
            text = self.tokenizer.decode(temp)
            if text==word:
                effective.append((text, temp))
            else:
                break
        effective.sort(key=lambda x: len(x[1]))
        return effective[0][1]

class HuggingfaceCore(BaseCore):
    """This is the core class of loading model in awq, gptq, or original format.
    """
    def __init__(self, model_id: str, model_type: Literal['default', 'awq', 'gptq'], model_kwargs: Dict[str, Any] = dict(), tokenizer_kwargs: Dict[str, Any] = dict()) -> None:
        """Initiating the core with transformers.

        Args:
            model_id (str): Model id (from Huggingface) to use.
            model_type (Literal[&#39;default&#39;, &#39;awq&#39;, &#39;gptq&#39;]): Type of model format.
            model_kwargs (Dict[str, Any], optional): Keyword arguments for loading the model. Defaults to dict().
            tokenizer_kwargs (Dict[str, Any], optional): Keyword arguments for loading the tokenizer. Defaults to dict().
        """
        from ...utils import get_config
        os.environ['HF_HOME'] = get_config()['hf_home']
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self._model_id = model_id
        self._core_type = 'HuggingfaceCore'
        self._model_type = model_type

        if not hasattr(tokenizer_kwargs, 'pretrained_model_name_or_path'):
            tokenizer_kwargs['pretrained_model_name_or_path'] = model_id
        self._tokenizer = AutoTokenizer.from_pretrained(**tokenizer_kwargs)

        if not hasattr(model_kwargs, 'device_map'):
            model_kwargs['device_map'] = 'auto'
        model_kwargs['pretrained_model_name_or_path'] = model_id
        self._model = AutoModelForCausalLM.from_pretrained(**model_kwargs)

    @property
    def model_type(self) -> str:
        """Format of the model.

        Returns:
            str: Format of the model.
        """
        return self._model_type
    
    def unload(self) -> None:
        """Unload the model from ram."""
        device = self._model.device
        del self._model
        self._model = None
        del self._tokenizer
        self._tokenizer = None
        if 'cuda' in device:
            import torch
            torch.cuda.empty_cache()
    
class HuggingfaceLLM(BaseLLM):
    '''Custom implementation of streaming for models loaded with `llama-cpp-python`, Used in the Llm factory to get new llm from the model.'''
    core: HuggingfaceCore
    generation_config: Dict[str, Any]
    stop: List[str]

    def __init__(self, core: HuggingfaceCore, temperature: float = 0, max_new_tokens: int = 2048, top_p: float = 0.95, top_k: int = 40, 
                 repetition_penalty: float = 1.1, stop: Optional[List[str]] = None, stop_newline_version: bool = True) -> None:
        """Initialising the llm.

        Args:
            core (LlamaCppCore): The LlamaCppCore core.
            temperature (float, optional): Set how "creative" the model is, the smaller it is, the more static of the output. Defaults to 0.
            max_new_tokens (int, optional): Maximum number of tokens to generate by the llm. Defaults to 2048.
            top_p (float, optional): While sampling the next token, only consider the tokens above this p value. Defaults to 0.95.
            top_k (int, optional): While sampling the next token, only consider the top "top_k" tokens. Defaults to 40.
            repetition_penalty (float, optional): The value to penalise the model for generating repetitive text. Defaults to 1.1.
            stop (Optional[List[str]], optional): List of strings to stop the generation of the llm. Defaults to None.
            stop_newline_version (bool, optional): Whether to add duplicates of the list of stop words starting with a new line character. Defaults to True.
        """
        from .utils import get_stop_words
        stop = get_stop_words(stop, core.tokenizer, stop_newline_version, 'transformers')

        generation_config = dict(
            temperature = temperature if temperature != 0 else 0.01,
            do_sample = False if temperature == 0 else True,
            max_new_tokens = max_new_tokens,
            top_p  = top_p,
            top_k = top_k,
            repetition_penalty = repetition_penalty
        )

        super().__init__(core=core, generation_config=generation_config, stop=stop)
        self.generation_config = generation_config
        self.core = core
        self.stop = stop

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Dict[str, Any],
    ) -> Union[str, Iterator[str]]:
        """Text generation of the llm. Return the generated string given the prompt. If set `stream=True`, return a python generator that yield the tokens one by one.

        Args:
            prompt (str): The prompt to the llm.
            stop (Optional[List[str]], optional): List of strings to stop the generation of the llm. If provided, it will overide the original llm stop list. Defaults to None.
            run_manager (Optional[CallbackManagerForLLMRun], optional): Not used. Defaults to None.

        Returns:
            Union[str, Iterator]: The output string or a python generator, depending on if it's in stream mode.

        Yields:
            Iterator[str]: The next generated token.
        """
        from .utils import get_stop_words, textgen_iterator
        import warnings
        warnings.filterwarnings('ignore')
        stop = get_stop_words(stop, tokenizer=self.core.tokenizer, add_newline_version=False, tokenizer_type='transformers') if stop is not None else self.stop
        stream = kwargs.get('stream', False)
        gen_config = self.generation_config.copy()
        gen_config['stopping_criteria'] = StoppingCriteriaList([KeywordsStoppingCriteria(stop, self.core.tokenizer)])
        for k, v in kwargs.items():
            if k == 'temperature':
                if v > 0:
                    gen_config['temperature'] = v
                    gen_config['do_sample'] = True
                else:
                    gen_config['temperature'] = 0.01
                    gen_config['do_sample'] = False
            elif k in ['max_new_tokens', 'top_p', 'top_k', 'repetition_penalty']:
                gen_config[k] = v
                
        if stream:
            from threading import Thread
            from transformers import TextIteratorStreamer
            gen_config['streamer'] = TextIteratorStreamer(tokenizer=self.core.tokenizer, skip_prompt=True)
            
            def pipe(prompt):
                tokens = self.core.tokenizer(
                    prompt,
                    return_tensors='pt'
                ).input_ids.to(self.core.model.device)
                output = self.core.model.generate(tokens, **gen_config)
            
            trd = Thread(target=pipe, args=[prompt])
            def generate():
                trd.start()
                for i in gen_config['streamer']:
                    yield i
                trd.join()
                yield ''
            return textgen_iterator(generate(), stop=stop)
        
        else:
            from langchain.llms.utils import enforce_stop_tokens
            def pipe(prompt):
                tokens = self.core.tokenizer(
                    prompt,
                    return_tensors='pt'
                ).input_ids.to(self.core.model.device)
                output = self.core.model.generate(tokens, **gen_config)
                return self.core.tokenizer.decode(output[0], skip_special_tokens=True).removeprefix(prompt)

            output = pipe(prompt)
            output = enforce_stop_tokens(output, stop)
            del pipe
            return output

    def _llm_type(self) -> str:
        """LLM type.

        Returns:
            str: LLM type.
        """
        return 'HuggingfaceLLM'