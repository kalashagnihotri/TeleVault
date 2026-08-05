import os
import re

path = 'src/face_analysis.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the new method
new_method = '''
    def _calculate_person_scores(self, embedding, top_k: int):
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

# Find the class FaceAnalysisWorker to insert the new method
# We will insert it before analyze_image
content = content.replace('    def analyze_image(self,', new_method + '\n    def analyze_image(self,')

# Replace the block from if self.calibration_snapshot: to else: decision = "UNKNOWN_UNCALIBRATED" ...
# Wait, let's use a regex or manual string replacement.
c1 = '''                if self.calibration_snapshot:
                    scores_by_person = {}
                    for ref in self.ref_snapshot:
                        pid = ref["person_id"]
                        score = self.engine.compare_embeddings(embedding, ref["embedding"])
                        score = _to_float(score)
                        if pid not in scores_by_person:
                            scores_by_person[pid] = []
                        scores_by_person[pid].append(score)
                        
                    # Calculate aggregates
                    person_max_scores = {}
                    person_aggregate_scores = {}
                    top_k = self.config.faces.aggregate_top_k
                    for pid, scores in scores_by_person.items():
                        person_max_scores[pid] = max(scores)
                        sorted_scores = sorted(scores, reverse=True)
                        top_scores = sorted_scores[:min(top_k, len(sorted_scores))]
                        person_aggregate_scores[pid] = sum(top_scores) / len(top_scores)
                        
                    sorted_people = sorted(person_aggregate_scores.items(), key=lambda x: x[1], reverse=True)'''

r1 = '''                diagnostic_data = {}
                if self.ref_snapshot:
                    top_k = self.config.faces.aggregate_top_k
                    scores_by_person, person_max_scores, person_aggregate_scores, sorted_people = self._calculate_person_scores(embedding, top_k)
                else:
                    scores_by_person, person_max_scores, person_aggregate_scores, sorted_people = {}, {}, {}, []'''
content = content.replace(c1, r1)

c2 = '''                    diagnostic_data = {
                        "scores_by_person": scores_by_person,
                        "person_max_scores": person_max_scores,
                        "person_aggregate_scores": person_aggregate_scores,
                        "sorted_people": sorted_people
                    }'''
r2 = '''                diagnostic_data.update({
                    "scores_by_person": scores_by_person,
                    "person_max_scores": person_max_scores,
                    "person_aggregate_scores": person_aggregate_scores,
                    "sorted_people": sorted_people
                })'''
content = content.replace(c2, r2)

c3 = '''                    if len(sorted_people) > 0:
                        best_person_id = sorted_people[0][0]
                        best_score = sorted_people[0][1]
                        
                    if len(sorted_people) > 1:
                        second_best_person_id = sorted_people[1][0]
                        second_best_score = sorted_people[1][1]
                        score_margin = best_score - second_best_score
                    elif len(sorted_people) == 1:
                        score_margin = best_score'''
r3 = '''                if len(sorted_people) > 0:
                    best_person_id = sorted_people[0][0]
                    best_score = sorted_people[0][1]
                    
                if len(sorted_people) > 1:
                    second_best_person_id = sorted_people[1][0]
                    second_best_score = sorted_people[1][1]
                    score_margin = best_score - second_best_score
                elif len(sorted_people) == 1:
                    score_margin = best_score'''
content = content.replace(c3, r3)

# Now for the threshold checking, we put it under if self.calibration_snapshot:
c4 = '''                    if best_person_id is not None:
                        ref_count = len(scores_by_person[best_person_id])
                        support_at_review = sum(1 for s in scores_by_person[best_person_id] if s >= self.calibration_snapshot["review_threshold"])
                        support_at_accept = sum(1 for s in scores_by_person[best_person_id] if s >= self.calibration_snapshot["accept_threshold"])
                        support_at_strong = sum(1 for s in scores_by_person[best_person_id] if s >= self.calibration_snapshot["individual_strong_support_threshold"])
                        supporting_count = support_at_strong
                        
                        diagnostic_data["support_at_review"] = support_at_review
                        diagnostic_data["support_at_accept"] = support_at_accept
                        diagnostic_data["support_at_strong"] = support_at_strong
                        diagnostic_data["maximum_individual_score"] = person_max_scores[best_person_id]
                        diagnostic_data["top_k_aggregate_score"] = best_score
                        diagnostic_data["aggregate_second_best_score"] = second_best_score if second_best_score >= 0 else None
                        diagnostic_data["aggregate_margin"] = score_margin
                        
                        if ref_count < top_k:
                            decision = "UNKNOWN_INSUFFICIENT_REFERENCES"
                            res.unknown_faces += 1
                        elif best_score < self.calibration_snapshot["review_threshold"]:
                            decision = "UNKNOWN_LOW_SCORE"
                            res.unknown_faces += 1
                        elif best_score < self.calibration_snapshot["accept_threshold"]:
                            decision = "UNKNOWN_AMBIGUOUS"
                            res.unknown_faces += 1
                        elif score_margin < self.calibration_snapshot["minimum_margin"]:
                            decision = "UNKNOWN_AMBIGUOUS"
                            res.unknown_faces += 1
                        elif support_at_strong < self.config.faces.minimum_strong_support:
                            decision = "UNKNOWN_INSUFFICIENT_SUPPORT"
                            res.unknown_faces += 1
                        else:
                            decision = "KNOWN_MATCH"
                            res.accepted_faces += 1
                    else:
                        decision = "UNKNOWN_LOW_SCORE"
                        res.unknown_faces += 1
                else:
                    decision = "UNKNOWN_UNCALIBRATED"
                    res.unknown_faces += 1'''
r4 = '''                if best_person_id is not None:
                    diagnostic_data["maximum_individual_score"] = person_max_scores[best_person_id]
                    diagnostic_data["top_k_aggregate_score"] = best_score
                    diagnostic_data["aggregate_second_best_score"] = second_best_score if second_best_score >= 0 else None
                    diagnostic_data["aggregate_margin"] = score_margin
                    
                    if self.calibration_snapshot:
                        ref_count = len(scores_by_person[best_person_id])
                        support_at_review = sum(1 for s in scores_by_person[best_person_id] if s >= self.calibration_snapshot["review_threshold"])
                        support_at_accept = sum(1 for s in scores_by_person[best_person_id] if s >= self.calibration_snapshot["accept_threshold"])
                        support_at_strong = sum(1 for s in scores_by_person[best_person_id] if s >= self.calibration_snapshot["individual_strong_support_threshold"])
                        supporting_count = support_at_strong
                        
                        diagnostic_data["support_at_review"] = support_at_review
                        diagnostic_data["support_at_accept"] = support_at_accept
                        diagnostic_data["support_at_strong"] = support_at_strong
                        
                        if ref_count < top_k:
                            decision = "UNKNOWN_INSUFFICIENT_REFERENCES"
                            res.unknown_faces += 1
                        elif best_score < self.calibration_snapshot["review_threshold"]:
                            decision = "UNKNOWN_LOW_SCORE"
                            res.unknown_faces += 1
                        elif best_score < self.calibration_snapshot["accept_threshold"]:
                            decision = "UNKNOWN_AMBIGUOUS"
                            res.unknown_faces += 1
                        elif score_margin < self.calibration_snapshot["minimum_margin"]:
                            decision = "UNKNOWN_AMBIGUOUS"
                            res.unknown_faces += 1
                        elif support_at_strong < self.config.faces.minimum_strong_support:
                            decision = "UNKNOWN_INSUFFICIENT_SUPPORT"
                            res.unknown_faces += 1
                        else:
                            decision = "KNOWN_MATCH"
                            res.accepted_faces += 1
                    else:
                        decision = "UNKNOWN_UNCALIBRATED"
                        res.unknown_faces += 1
                else:
                    if self.calibration_snapshot:
                        decision = "UNKNOWN_LOW_SCORE"
                    else:
                        decision = "UNKNOWN_UNCALIBRATED"
                    res.unknown_faces += 1'''
content = content.replace(c4, r4)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
