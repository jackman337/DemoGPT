import json
import os
import re

from langchain import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.prompts.chat import (ChatPromptTemplate,
                                    HumanMessagePromptTemplate,
                                    SystemMessagePromptTemplate)

from demogpt.controllers import checkDTypes, checkAppTypeCompatiblity, checkRedundantTasks
from demogpt.utils import refine

from . import prompts
from demogpt.chains.task_definitions import getTasks, getPlanGenHelper

class Chains:
    @classmethod
    def setLlm(
        cls,
        model,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        temperature=0.0,
        openai_api_base=None,
    ):
        cls.llm = ChatOpenAI(
            model=model,
            openai_api_key=openai_api_key,
            temperature=temperature,
            openai_api_base=openai_api_base,
        )

    @classmethod
    def getChain(cls, system_template="", human_template="", **kwargs):
        prompts = []
        if system_template:
            prompts.append(SystemMessagePromptTemplate.from_template(system_template))
        if human_template:
            prompts.append(HumanMessagePromptTemplate.from_template(human_template))
        chat_prompt = ChatPromptTemplate.from_messages(prompts)
        return LLMChain(llm=cls.llm, prompt=chat_prompt).run(**kwargs)

    @classmethod
    def appType(cls, instruction):
        app_type =  cls.getChain(
            system_template=prompts.app_type.system_template,
            human_template=prompts.app_type.human_template,
            instruction=instruction,
        )
        
        return json.loads(app_type)
    
    @classmethod
    def systemInputs(cls, instruction):
        return cls.getChain(
            system_template=prompts.system_inputs.system_template,
            human_template=prompts.system_inputs.human_template,
            instruction=instruction,
        )

    @classmethod
    def plan(cls, instruction):
        return cls.getChain(
            system_template=prompts.plan.system_template,
            human_template=prompts.plan.human_template,
            instruction=instruction,
        )

    @classmethod
    def planWithInputs(cls, instruction, system_inputs, app_type):
        TASK_DESCRIPTIONS, TASK_NAMES, TASK_DTYPES = getTasks(app_type)
        helper = getPlanGenHelper(app_type)
        plan = cls.getChain(
            system_template=prompts.plan_with_inputs.system_template,
            human_template=prompts.plan_with_inputs.human_template,
            instruction=instruction,
            system_inputs=system_inputs,
            helper=helper,
            TASK_DESCRIPTIONS=TASK_DESCRIPTIONS,
            TASK_NAMES=TASK_NAMES,
            TASK_DTYPES=TASK_DTYPES
        )
        return cls.refinePlan(plan)
    
    @classmethod
    def planFeedback(cls, instruction, plan):        
        feedback = cls.getChain(
            system_template=prompts.plan_feedback.system_template,
            human_template=prompts.plan_feedback.human_template,
            instruction=instruction,
            plan=plan
        )
        
        return json.loads(feedback)
    
    @classmethod
    def planRefiner(cls, instruction, plan, feedback):
        return cls.getChain(
            system_template=prompts.plan_refiner.system_template,
            human_template=prompts.plan_refiner.human_template,
            instruction=instruction,
            plan=plan,
            feedback=feedback
        )

    @classmethod
    def tasks(cls, instruction, plan, app_type):
        TASK_DESCRIPTIONS, TASK_NAMES, _ = getTasks(app_type)
        
        task_list = cls.getChain(
            system_template=prompts.tasks.system_template,
            human_template=prompts.tasks.human_template,
            instruction=instruction,
            plan=plan,
            TASK_DESCRIPTIONS=TASK_DESCRIPTIONS,
            TASK_NAMES=TASK_NAMES
        )
        return json.loads(task_list)

    @classmethod
    def taskController(cls, tasks, app_type):
        dtype_feedback = checkDTypes(tasks)
        app_type_feedback = checkAppTypeCompatiblity(tasks, app_type)
        redundant_task_feedback = checkRedundantTasks(tasks)
        
        feedback = dtype_feedback["feedback"] + "\n\n" + app_type_feedback["feedback"] + "\n\n" + redundant_task_feedback["feedback"]
        valid = dtype_feedback["valid"] and app_type_feedback["valid"] and redundant_task_feedback["valid"]
        
        return {
            "feedback":feedback,
            "valid":valid
        }
        

    @classmethod
    def refineTasks(cls, instruction, tasks, feedback, app_type):
        TASK_DESCRIPTIONS, _, _ = getTasks(app_type)
        
        task_list = cls.getChain(
            system_template=prompts.task_refiner.system_template,
            human_template=prompts.task_refiner.human_template,
            instruction=instruction,
            tasks=tasks,
            feedback=feedback,
            TASK_DESCRIPTIONS=TASK_DESCRIPTIONS
        )

        return json.loads(task_list)

    @classmethod
    def combine(cls, instruction, code_snippets, plan):
        code = cls.getChain(
            system_template=prompts.combine.system_template,
            human_template=prompts.combine.human_template,
            instruction=instruction,
            code_snippets=code_snippets,
            plan=plan,
        )
        return refine(code)

    @classmethod
    def combine_v2(cls, code_snippets, function_names):
        code = cls.getChain(
            system_template=prompts.combine_v2.system_template,
            human_template=prompts.combine_v2.human_template,
            code_snippets=code_snippets,
            function_names=function_names
        )
        return refine(code)

    @classmethod
    def feedback(cls, instruction, code):
        return cls.getChain(
            system_template=prompts.feedback.system_template,
            human_template=prompts.feedback.human_template,
            instruction=instruction,
            code=code,
        )
        
    @classmethod
    def refinePlan(cls, plan):
        pattern = r'\[[a-zA-Z0-9_]+\(.*\)'
        steps = plan.strip().split("\n")
        refined_plan = []
        index = 1
        for i in range(len(steps)):
            step = steps[i]
            # If current step contains the pattern or next step contains the pattern, then retain
            if re.search(pattern, step):
                # Remove existing numbering
                current_step = re.sub(r'^\d+\.', "", step).strip()
                refined_plan.append(f"{index}. {current_step}")
                index += 1
        return "\n".join(refined_plan)
    
    @classmethod
    def refine(cls, instruction, code, feedback):
        code = cls.getChain(
            system_template=prompts.refine.system_template,
            human_template=prompts.refine.human_template,
            instruction=instruction,
            code=code,
            feedback=feedback,
        )
        return refine(code)

    @classmethod
    def final(cls, draft_code):
        code = cls.getChain(
            system_template=prompts.final.system_template,
            human_template=prompts.final.human_template,
            draft_code=draft_code,
        )
        return refine(code)
