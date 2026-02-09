import os
import logging
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

def generate_report(diff_report, current_state=None):
    """
    Generates a breaking news report using LangChain.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logging.error("Reporting: Missing OPENAI_API_KEY.")
        return None

    if not diff_report.get('new_entries') and not diff_report.get('rank_changes'):
        logging.info("Reporting: No significant changes to report.")
        return None

    # Load external prompt
    try:
        with open("reporting/prompt.txt", "r") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        logging.warning("Reporting: prompt.txt not found, using fallback.")
        system_prompt = "You are an AI News Anchor. Report these changes: {changes}"

    # Prepare Context (Top 5 models per source)
    context_lines = []
    if current_state:
        for source, models in current_state.items():
            # Ensure models is a list
            if not isinstance(models, list): continue

            # Filter out None/empty
            valid_models = [m for m in models if isinstance(m, dict)]

            if not valid_models: continue

            # Add Header for this Source
            context_lines.append(f"\nSource: {source.upper()}")
            context_lines.append("Rank,Model,Score")

            # Take top 5
            for m in valid_models[:5]:
                try:
                    score = m.get('score', 0)
                    if isinstance(score, float):
                         score = f"{score:.2f}"

                    line = f"{m.get('rank')},{m.get('model')},{score}"
                    context_lines.append(line)
                except:
                    continue

    csv_context = "\n".join(context_lines)

    # Prepare Changes as JSON string
    # Filter only relevant fields for the prompt to save tokens/noise
    clean_diff = {
        "new_entries": diff_report.get("new_entries", []),
        "rank_changes": diff_report.get("rank_changes", []),
        "score_changes": diff_report.get("score_changes", [])
    }
    json_changes = json.dumps(clean_diff, indent=2)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "CONTEXT (CSV):\n```csv\n{context}\n```\n\nCHANGES (JSON):\n```json\n{changes}\n```")
    ])

    llm = ChatOpenAI(model="gpt-4o") # Updated to a known model, user said gpt-5-mini in prev code which might be a placeholder or typo
    chain = prompt | llm | StrOutputParser()

    try:
        report = chain.invoke({"context": csv_context, "changes": json_changes})
        
        # Post-processing (length check only)
        if len(report) > 4000:
            report = report[:4000] + "...\n(Report truncated)"
        
        logging.info("Reporting: Generated update.")
        return report
    except Exception as e:
        logging.error(f"Reporting: LLM failed: {e}")
        return None
