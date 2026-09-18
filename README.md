# ai-safety-governance
Materials, Notes &amp; Portfolio

# OWASP 2025 Top 10 Risks & Mitigation: 
https://genai.owasp.org/llm-top-10/

---

# LLM01:2025 Prompt Injection

## Main Takeaway : User prompts alter LLM's behavior or output in unintended ways. Prompts do no need to be human-visible/readable, PARSE-ABLE by the model. 

1. How models process prompts
2. How input may force model to incorrectly pass prompts to other parts of model.
(result in: violate guidelines, generate harmful content, enable unauthorized access, influence critical decisions)
eg.
  1. Mental health chatbot (Lakera Gandalf's Solace AI) tricked to use profane words.
  2. Travel websites: Putting hidden prompts for agent manipulates information gathering.
  3. Tricking agents to provide confidential database information.

RAG (Retrieval Augmented Generation) & fine-tuning makes LLM outputs more relevant & accurate, but doesn't fully mitigate these vulnerabilities.

## Solution : SAFEGUARDS into system prompts and input handling. 
(Requires ongoing updates to model's training and safety mechanisms.)

--- 

### QN: Difference between Prompt Injection & Jailbreaking?

Prompt injection involves manipulating model responses through specific inputs to alter its behavior, which can include bypassing safety measures.


Jailbreaking is a form of prompt injection where the attacker provides inputs that cause the model to disregard its safety protocols entirely.
