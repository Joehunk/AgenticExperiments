# Structured Output
Both OpenAI and LangGraph can specify a Pydantic model for structured output, but they don't automatically try to validate it. They will put any data they want in there and if validation fails, that shows up as an exception thrown
after the LLM has already returned its response.

There is some evidence that the LLM is not a-priori prompted with the schema of the expected output but rather
it takes whatever response it comes up with and attempts to structure it that way. Therefore,
we cannot rely on structured output to give "Instructor like" behavior, i.e. to prompt an LLM to
structure output in a certain way and keep asking questions if it cannot. We have to give it access to
the expected schema (it seems).

## Update
After some research it DOES appear that the LLM is fed the structure of the expected output under
the hood. So it must be a prompting problem.
