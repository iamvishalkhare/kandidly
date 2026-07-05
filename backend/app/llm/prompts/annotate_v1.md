Given one candidate answer, the question asked, and the rubric criteria list,
emit 0–3 annotations: which criteria this answer gives signal on, direction
(strong_positive…unclear), and a ≤25-word note naming the concrete signal
("explained idempotency keys with retry semantics"). No annotation is the
correct output for chit-chat. Criteria: {criteria_digest}
Q: {question}  A: {answer}
