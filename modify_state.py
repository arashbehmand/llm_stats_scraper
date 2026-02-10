import json
import os

STATE_FILE = "state/last_run.json"


def modify_state():
    if not os.path.exists(STATE_FILE):
        print(f"Error: {STATE_FILE} not found. Please run main.py once first.")
        return

    with open(STATE_FILE, "r") as f:
        data = json.load(f)

    print("Modifying state...")

    # Models to remove by name
    models_to_remove = ["gemini-3-pro", "Gemini 3 Pro", "Gemini 3 Pro Preview (high)"]

    for source, models in data.items():
        if not isinstance(models, list):
            continue

        # Remove models by name
        len(models)
        models_copy = models.copy()
        for model_entry in models_copy:
            if model_entry.get("model") in models_to_remove:
                models.remove(model_entry)
                print(
                    f"[{source}] Removed: {model_entry['model']} (rank #{model_entry.get('rank', 'N/A')})"
                )

        data[source] = models  # Update with filtered list

        # # PREVIOUS RANK-BASED LOGIC (commented out):
        # # Sort by rank just in case (though should be sorted)
        # models.sort(key=lambda x: x['rank'])
        #
        # # We want to remove 3rd (index 2) and 5th (index 4)
        # # Note: If we pop(2), the indices shift!
        # # So we should pop(4) first (which is index 4), then pop(2).
        #
        # if len(models) > 4:
        #     removed_5 = models.pop(4)
        #     print(f"[{source}] Removed #{removed_5['rank']}: {removed_5['model']}")
        #
        # if len(models) > 2:
        #     removed_3 = models.pop(2)
        #     print(f"[{source}] Removed #{removed_3['rank']}: {removed_3['model']}")

    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nState modified and saved to {STATE_FILE}")
    print("Run 'python main.py' to see the diff report.")


if __name__ == "__main__":
    modify_state()
