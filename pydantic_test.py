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
        This field indicates whether the agent was able to successfully fill out the form data
        """
    )
    result: t.Union[TestModel, str] = Field(
        description="""
        This field represents the result of an attempt by the agent to fill out the form in a way that conforms
        to a specific Python type. If the agent is able to generate a valid data, including successfully running
        the supplied validation tool, then this field should contain a Python object the the form data.
        If the agent needs user feedback to be able to fill out the form or correct a validation error,
        then this field should contain a string that will be sent directly to the user that explains
        the issue and asks for their input.
        """)
    
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


TOOL_BASED_PROMPT_AGENT_AGNOSTIC = """
You are an agent whose job is to take unstructured user input and format it to a supplied schema.

The schema allows two statuses:
- SUCCESS: This means you were able to structure the data successfully. The result should be set
  to the structured data.
- USER_INPUT_NEEDED: This means you need more information from the user to be able to structure the data.
  The result should be set to a string message that will be sent directly to the user explaining what 
  you need from them.

CRITICAL: You must ALWAYS call the validation tool you have available before returning a SUCCESS status.

IMPORTANT: Do not ask the user for information you don't need. If you have enough information to
conform to the structured output format (including all required fields) and the validation tool passes,
you are done.

KEY PRINCIPLE: You should automatically handle minor formatting corrections without user input, including:
- Capitalization adjustments (e.g., proper case for names, uppercase for state codes)
- Phone number reformatting (e.g., adding/removing dashes, parentheses, country codes)
- Date format standardization
- Whitespace trimming and normalization
- Common abbreviation expansions or standardizations
- Postal/ZIP code formatting
- Obvious typos with a single likely correction

Only use USER_INPUT_NEEDED status when:
- Required fields are missing or ambiguous
- Data conflicts or is logically inconsistent
- Multiple interpretations exist and you cannot determine the correct one
- The provided information is genuinely invalid (not just incorrectly formatted)

Remember: Your role is to STRUCTURE and FORMAT data, not to burden the user with trivial formatting decisions.
If you can reasonably infer and correct the formatting to match the schema, do so automatically.
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
    llm = ChatAnthropic(model="claude-sonnet-4-20250514", anthropic_api_key=os.getenv("ANTHROPIC_KEY"))
    react_agent = create_react_agent(
        model=llm,
        tools=[validate_model_langgraph],
        prompt=TOOL_BASED_PROMPT_AGENT_AGNOSTIC,
        response_format=FormResult
    )

    if fresh_start or not os.path.exists('./langgraph_last_state.json'):
        messages = []
    else:
        with open('./langgraph_last_state.json', 'r') as f:
            json_messages = json.load(f)
            messages = messages_from_dict(json_messages)
    messages += [HumanMessage(content=user_input)]

    result = await react_agent.ainvoke({"messages": messages})
    with open('./langgraph_last_state.json', 'w') as f:
        json_messages = messages_to_dict(result['messages'])
        json.dump(json_messages, f)
    print(result['structured_response'])

if __name__ == "__main__":
    import argparse

    dotenv.load_dotenv()
    set_tracing_disabled(True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--continue", "-c", type=bool, required=False, default=False, dest="continue_flag")
    parser.add_argument('prompt', nargs='*', help='The prompt')
    args = parser.parse_args()

    asyncio.run(test_with_langgraph(' '.join(args.prompt), fresh_start=not args.continue_flag))
