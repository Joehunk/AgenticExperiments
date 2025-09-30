import uuid
from pydantic import BaseModel, ValidationError, field_validator, Field, ValidationInfo
import os
import asyncio
import dotenv
import typing as t
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, messages_to_dict, messages_from_dict
import pickle
import json
import instructor
import anthropic
import pprint

from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel

class TestModel(BaseModel):
    name: str = Field(description="Name of the user", max_length=32)

    @field_validator("name")
    def validate_name(cls, value: str, info: ValidationInfo) -> str:
        split_name = value.split(' ')
        if len(split_name) != 2:
            raise ValueError(f'The name must have a first and last name, and no additional tokens. You passed in {len(split_name)} tokens: "{value}"')
        for name_part in split_name:
            if name_part != name_part.capitalize():
                raise ValueError(f'Names must be capitalized. {name_part} is not capitalized.')
        first_name, _ = split_name
        if first_name != "Bob":
            raise ValueError(f"Only people with the first name of Bob are supported. You supplied: {first_name}")
        return value
    
class FormResult(BaseModel):
    status: t.Literal["SUCCESS", "USER_INPUT_NEEDED"] = Field(
        description="""
        This field indicates whether the agent was able to successfully fill out the form data.

        SUCESS indicates that the agent was able to fill out the form data, and result will contain
        the filled out data.

        USER_INPUT_NEEDED indicates that the agent was not able to fill out the form data, and result
        will contain a string that will be sent to the user to get additional information. The agent
        will then be invoked again with the user's response, and should continue to do so until it is able
        to fill out the form data.
        """
    )
    final_result: TestModel | None = Field(
        default=None,
        description="This field contains the filled out form data if status is SUCCESS. Otherwise it is null."
    )
    user_prompt: str | None = Field(
        default=None,
        description="This field contains a prompt to be sent to the user if status is USER_INPUT_NEEDED. Otherwise it is null."
    )
    
@function_tool(strict_mode=False)
def validate_model_openai(json_dict: dict[str, t.Any]) -> t.Union[TestModel, ValidationError]:
    """
    Validates a JSON dictionary against the TestModel schema using Pydantic.

    Args:
        json_dict (dict[str, Any]): The JSON data represented as a Python dictionary to validate.

    Returns:
        Union[TestModel, ValidationError]: A validated TestModel instance if validation succeeds,
        otherwise a ValidationError describing the validation issues.

    Example:
        validate_model_openai({"field1": "value", "field2": 123})
        # Returns: <TestModel instance or ValidationError>
    """
    print(f'validating: {json_dict}')
    try:
        return TestModel.model_validate(json_dict)
    except ValidationError as e:
        return e
    
@tool(parse_docstring=True, error_on_invalid_docstring=True)
def validate_model_langgraph(
    json_dict: t.Annotated[dict[str, t.Any], "A JSON object representing raw form data to be validated."]
) -> t.Union[TestModel, ValidationError]:
    """
    Validates a JSON dictionary against the TestModel schema using Pydantic.

    Args:
        json_dict (dict[str, Any]): The JSON data represented as a Python dictionary to validate.

    Returns:
        Union[TestModel, ValidationError]: A validated TestModel instance if validation succeeds,
        otherwise a ValidationError describing the validation issues.

    Example:
        validate_model_openai({"field1": "value", "field2": 123})
        # Returns: <TestModel instance or ValidationError>
    """
    print(f'validating: {json_dict}')
    try:
        return TestModel.model_validate(json_dict)
    except ValidationError as e:
        return e


TOOL_BASED_PROMPT_AGENT_AGNOSTIC = f"""
You are an agent whose goal is to take unstructured user input and format it into a structured form.

CRITICAL: Always review the entire conversation history before responding. Information provided in ANY previous turn must be used and should never be requested again. Before asking for any information, first check if it has already been provided in earlier messages.

You are configured for structured output, and you have access to a tool that can validate your output.
You MUST supply output corresponding to the output schema, and you MUST use the tool to validate your output.

CONVERSATION MEMORY RULES:
- Maintain a running mental inventory of ALL information provided across all conversation turns
- Before asking any question, mentally review: "What has the user already told me?"
- Build upon previous responses incrementally - each turn should add to, not restart, the data collection
- If information seems missing, double-check the conversation history before requesting it

BEFORE EACH RESPONSE:
1. Review ALL previous conversation turns
2. Identify what information has already been provided
3. Review what you have learned from previous validation attempts
4. Determine what information is still needed
5. Only ask for information that has NOT been provided yet

If you need any information from the user to fill out the form, you MUST ask the user for that information - but ONLY if it hasn't been provided already.
Feel free to correct obvious errors such as typographical errors, capitalization errors, or formatting errors.
If it is not apparent how to correct an error, you MUST ask the user for clarification.

Remember: This is a multi-turn conversation. Never ask for information that has already been provided. 
Always build upon the accumulated information from the entire conversation history.

Here is the JSON schema for the structured output:

```json
{json.dumps(TestModel.model_json_schema(), indent=2)}
```
"""
    
async def test_with_openai_output_type():
    """
    NOTES:

    This method simply throws a validation error. Or rather if the name does not pass the validator,
    It simply throws a value error. In fact it does not even seem to be able to follow length constraints
    or things that are specified statically.
    """
    agent = Agent(
        name="Assistant",
        instructions="""
You are responsible for filling out a simple form. For now that form only needs a person's name.
Ask the user questions until you are able to fill out the form to the supplied output schema,
then return the results
        """,
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514", api_key=os.getenv("ANTHROPIC_KEY")),
        output_type=TestModel
    )

    result = await Runner.run(agent, "My name is Bob Untzuntzuntzuntzuntzuntzuntzuntzuntz.")
    print(result.final_output)

async def test_with_openai_with_tool(user_input: str):
    """
    NOTES:

    This appears to be a good approach. It was able to return valid form data,
    correct errors that were obvious (such as capitalization), and ask for input when not.

    I saw one bugaboo which is that the whole thing threw an exception when I had double quotes in the
    error message (in the constructor of a ValueError). Maybe we shiould have the validation tool
    return the error instead of throwing?

    Note to above: this seems to have fixed it.
    """
    agent = Agent(
        name="Assistant",
        instructions=TOOL_BASED_PROMPT_AGENT_AGNOSTIC,
        model=LitellmModel(model="anthropic/claude-sonnet-4-20250514", api_key=os.getenv("ANTHROPIC_KEY")),
        output_type=FormResult,
        tools=[validate_model_openai]
    )

    result = await Runner.run(agent, user_input)
    print(result.final_output)

async def test_with_langgraph(user_input: str, fresh_start: bool = True):
    """
    NOTES:
    """
    print(f'input: {user_input}')
    validate_model_langgraph.name
    llm = ChatAnthropic(model="claude-sonnet-4-20250514", anthropic_api_key=os.getenv("ANTHROPIC_KEY"))
    react_agent = create_react_agent(
        model=llm,
        tools=[validate_model_langgraph],
        prompt=TOOL_BASED_PROMPT_AGENT_AGNOSTIC,
        response_format=FormResult,
    )

    if fresh_start or not os.path.exists('./langgraph_last_state.json'):
        messages = []
        thread_id = uuid.uuid4().hex
    else:
        with open('./langgraph_last_v2_state.json', 'r') as f:
            json_messages = json.load(f)
            messages = messages_from_dict(json_messages['messages'])
            thread_id = json_messages['thread_id']
    messages += [HumanMessage(content=user_input)]

    result = await react_agent.ainvoke({"messages": messages}, config={"configurable": {"thread_id": thread_id}})
    with open('./langgraph_last_v2_state.json', 'w') as f:
        json_messages = messages_to_dict(result['messages'])
        json.dump({'messages': json_messages, 'thread_id': thread_id}, f, indent=2)
    print(result['structured_response'])
    
def test_with_instructor(user_input: str, fresh_start: bool = True):
    if fresh_start or not os.path.exists('./instructor_last_state.json'):
        messages = [
            {"role": "system", "content": """
Based on the user's input, return the filled out TestModel. If you cannot or the TestModel fails validation,
tell the user why you cannot in a UserPrompt message.

CRITICAL CONVERSATION HISTORY RULES:
1. BEFORE asking ANY question, you MUST:
   - Scan the entire conversation history for ALL previously provided information
   - Extract every piece of data the user has already shared
   - SYNTHESIZE related information from different conversation turns
   - INFER complete answers by combining partial information

2. INTELLIGENT INFORMATION SYNTHESIS:
   - If the user provides updates or modifications (e.g., "use X instead"), apply them to previously given information
   - Combine related data points from different turns to form complete answers
   - When user provides a variation or preference for existing data, merge it with what you already know
   - Example: If user said "my full info is A B C" then later says "use X for A", conclude the answer is "X B C"

3. NEVER ask for information that can be:
   - Found directly in conversation history
   - DERIVED by combining existing information
   - INFERRED from context and previous answers
   - Constructed from partial updates to previous data

4. Only ask for information when it is LOGICALLY IMPOSSIBLE to determine from existing conversation data.

5. If you must ask questions:
   - First state: "From our conversation, I have: [list what you know]"
   - Then specify ONLY what cannot be derived: "I still need: [truly missing piece]"

Remember: Users expect you to make obvious connections between related information across turns.
             """}
        ]
    else:
        with open('./instructor_last_state.json', 'r') as f:
            messages = json.load(f)
    messages.append({"role": "user", "content": user_input})

    pprint.pprint(messages)
    client = instructor.from_anthropic(anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_KEY"), timeout=60), mode=instructor.Mode.ANTHROPIC_REASONING_TOOLS)
    response = client.chat.completions.create(
        response_model=FormResult,
        messages=messages,
        max_retries=3,
        max_tokens=60000,
        temperature=0.2,
        model="claude-sonnet-4-20250514"
    )
    print(response)
    
    if response.user_prompt:
        messages.append({"role": "assistant", "content": response.user_prompt})
    
    with open('./instructor_last_state.json', 'w') as f:
        json.dump(messages, f, indent=2)

if __name__ == "__main__":
    import argparse

    dotenv.load_dotenv()
    set_tracing_disabled(False)

    parser = argparse.ArgumentParser()
    parser.add_argument("--continue", "-c", dest="continue_flag", action='store_true', help="Whether to continue from the last state (if available)")
    parser.add_argument('prompt', nargs='*', help='The prompt')
    args = parser.parse_args()

    # asyncio.run(test_with_langgraph(' '.join(args.prompt), fresh_start=not args.continue_flag))
    test_with_instructor(' '.join(args.prompt), fresh_start=not args.continue_flag)
