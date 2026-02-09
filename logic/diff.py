import logging
import json

class DiffEngine:
    def __init__(self, current_state, previous_state):
        self.current = current_state
        self.previous = previous_state
        self.report = {
            "summary": [],
            "new_entries": [],
            "rank_changes": [],
            "score_changes": []
        }

    def run(self):
        """
        Executes the diff logic across all sources.
        """
        if not self.previous:
            logging.info("DiffEngine: No previous state. First run.")
            return None

        for source_name, current_list in self.current.items():
            prev_list = self.previous.get(source_name, [])
            self._analyze_source(source_name, current_list, prev_list)

        return self.report

    def _analyze_source(self, source, current_list, prev_list):
        """
        Analyzes a single source (e.g. 'arena_text') for changes.
        """
        # Create lookups
        prev_map = {item['model']: item for item in prev_list}
        curr_map = {item['model']: item for item in current_list}

        # 1. Detect New Entries (in Top 20)
        for i, item in enumerate(current_list):
            rank = item['rank']
            model = item['model']

            # Skip invalid model names
            if not model or str(model).lower() in ['none', 'unknown', 'null']:
                continue

            if rank > 20: continue # Ignore noise below top 20

            if model not in prev_map:
                # NEW ENTRY!
                # Check context: who did it displace?
                displaced = self._find_displaced_model(rank, prev_list)
                context = f"Debuted at #{rank}"
                if displaced:
                    context += f", likely pushing {displaced} down."

                self.report['new_entries'].append({
                    "source": source,
                    "model": model,
                    "rank": rank,
                    "score": item['score'],
                    "context": context
                })
                self.report['summary'].append(f"[{source}] NEW: {model} at #{rank}")

            else:
                # 2. Detect Rank Changes
                prev_item = prev_map[model]
                prev_rank = prev_item['rank']

                if rank != prev_rank:
                    diff = prev_rank - rank # Positive = Improvement (e.g. 5 -> 3, diff=2)

                    # Filter noise: only report changes > 1 spot OR changes within Top 5
                    if abs(diff) >= 2 or (rank <= 5 or prev_rank <= 5):
                        direction = "CLIMBED" if diff > 0 else "DROPPED"
                        self.report['rank_changes'].append({
                            "source": source,
                            "model": model,
                            "old_rank": prev_rank,
                            "new_rank": rank,
                            "change": diff,
                            "context": f"{direction} {abs(diff)} spots (was #{prev_rank}, now #{rank})"
                        })
                        self.report['summary'].append(f"[{source}] {model} {direction} to #{rank} (was #{prev_rank})")

                # 3. Detect Score Spikes (e.g. +20 Elo)
                # Ensure scores are floats
                try:
                    curr_score = float(item['score'])
                    prev_score = float(prev_item['score'])
                    score_diff = curr_score - prev_score

                    # Threshold depends on scale.
                    # Arena uses Elo (1000-1300+). +10 is significant? Maybe +20.
                    # Vellum uses Elo/WinRate?
                    # LLMStats uses Elo?

                    # Heuristic: 2% change or > 20 points
                    if abs(score_diff) > 20:
                         self.report['score_changes'].append({
                            "source": source,
                            "model": model,
                            "old_score": prev_score,
                            "new_score": curr_score,
                            "diff": score_diff
                        })
                except (ValueError, TypeError):
                    pass

    def _find_displaced_model(self, rank, prev_list):
        """
        Finds which model was at this rank in the previous list.
        """
        for item in prev_list:
            if item['rank'] == rank:
                return item['model']
        return None

def run_diff(current, previous):
    engine = DiffEngine(current, previous)
    return engine.run()
