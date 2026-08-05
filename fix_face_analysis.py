import sys

path = 'src/face_analysis.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

import re

# 1. Update load_snapshots
c = c.replace('        ref_set_hash = hashlib.sha256("".join(ref_hashes).encode()).hexdigest() if ref_hashes else "empty"',
'''        base_ref_hash = hashlib.sha256("".join(ref_hashes).encode()).hexdigest() if ref_hashes else "empty"
        from src.hashing import get_calibration_scope_hash
        policy_id = self.config.faces.policy_identity
        ref_set_hash = get_calibration_scope_hash(model_identity, base_ref_hash, policy_id)''')

c = c.replace('                self.calibration_snapshot["minimum_margin"] = marg',
'''                self.calibration_snapshot["minimum_margin"] = marg
                self.calibration_snapshot["individual_strong_support_threshold"] = _to_float(calib.get("individual_strong_support_threshold", acc))''')

# 2. Add _calculate_person_scores method
method = '''    def _calculate_person_scores(self, embedding, top_k: int):
        scores_by_person = {}
        for ref in self.ref_snapshot:
            pid = ref["person_id"]
            score = self.engine.compare_embeddings(embedding, ref["embedding"])
            score = float(score)
            if pid not in scores_by_person:
                scores_by_person[pid] = []
            scores_by_person[pid].append(score)
            
        person_max_scores = {}
        person_aggregate_scores = {}
        for pid, scores in scores_by_person.items():
            person_max_scores[pid] = max(scores)
            sorted_scores = sorted(scores, reverse=True)
            top_scores = sorted_scores[:min(top_k, len(sorted_scores))]
            person_aggregate_scores[pid] = sum(top_scores) / len(top_scores)
            
        sorted_people = sorted(person_aggregate_scores.items(), key=lambda x: x[1], reverse=True)
        return scores_by_person, person_max_scores, person_aggregate_scores, sorted_people
'''

# We need to insert this method inside FaceAnalysisWorker
c = c.replace('    def _generate_analysis_key(self) -> tuple[str, int]:\n', method + '\n    def _generate_analysis_key(self) -> tuple[str, int]:\n')

# 3. Update _match_face to use _calculate_person_scores
match_face_old = '''        scores_by_person = {}
        for ref in self.ref_snapshot:
            pid = ref["person_id"]
            score = self.engine.compare_embeddings(embedding, ref["embedding"])
            if pid not in scores_by_person:
                scores_by_person[pid] = []
            scores_by_person[pid].append(float(score))
            
        if not scores_by_person:
            return "UNKNOWN_UNCALIBRATED", None, None, None, None, 0.0, 0
            
        person_max_scores = {pid: max(scores) for pid, scores in scores_by_person.items()}
        sorted_people = sorted(person_max_scores.items(), key=lambda x: x[1], reverse=True)
        
        best_person_id, best_score = sorted_people[0]
        second_best_person_id, second_best_score = sorted_people[1] if len(sorted_people) > 1 else (None, None)
        margin = best_score - second_best_score if second_best_score is not None else best_score
        
        # Filter strong support
        ind_thresh = self.calibration_snapshot.get("individual_strong_support_threshold", acc)
        strong_support = len([s for s in scores_by_person[best_person_id] if s >= ind_thresh])'''

match_face_new = '''        if not self.ref_snapshot:
            return "UNKNOWN_UNCALIBRATED", None, None, None, None, 0.0, 0

        scores_by_person, person_max_scores, person_aggregate_scores, sorted_people = self._calculate_person_scores(
            embedding,
            top_k=self.config.faces.aggregate_top_k
        )
        
        best_person_id, best_score = sorted_people[0]
        second_best_person_id, second_best_score = sorted_people[1] if len(sorted_people) > 1 else (None, None)
        margin = best_score - second_best_score if second_best_score is not None else best_score
        
        # Filter strong support using individual_strong_support_threshold
        ind_thresh = self.calibration_snapshot.get("individual_strong_support_threshold", acc) if self.calibration_snapshot else acc
        strong_support = len([s for s in scores_by_person[best_person_id] if s >= ind_thresh])'''

c = c.replace(match_face_old, match_face_new)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
