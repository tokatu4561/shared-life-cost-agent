from __future__ import annotations

from bedrock_agentcore import BedrockAgentCoreApp

from .receipt_agent import process_receipt

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    return process_receipt(payload)


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
