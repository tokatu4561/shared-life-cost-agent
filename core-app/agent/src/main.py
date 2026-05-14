from __future__ import annotations

from bedrock_agentcore import BedrockAgentCoreApp

from .expense_query_agent import process_expense_query
from .receipt_agent import process_receipt

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    if payload.get("task") == "expense_query":
        return process_expense_query(payload)
    return process_receipt(payload)


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
