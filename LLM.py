import google.generativeai as genai

def evaluate_claim_with_llm(claim_text, search_results, llm_model=genai.GenerativeModel()):
    """Uses Google Gemini to evaluate the claim based on search results."""
    print(f"Evaluating claim using LLM: '{claim_text.split('#', 1)[0].strip()}...'")
    if not search_results:
        print("WARNING: No search results provided to LLM. Evaluation may be unreliable.")
        return {"rating": "Cannot Verify", "reasoning": "No search results available to verify the claim."}
    prompt = f"""
    Please act as a neutral and critical fact-checker. Your task is to evaluate the truthfulness of the following content, which may be a short social media post or tweet. The original post and search results may be in Swedish, and your output should also be in Swedish.

    Instructions:
    1. First, determine if the post contains one or more factual claims. If it doesn't contain any verifiable claims, clearly state that no evaluation can be made.
    2. If there are claims, extract them and evaluate their truthfulness individually or as a whole depending on how they relate to each other.
    3. When reviewing the provided search result snippets:
    - Prioritize content from credible, authoritative, and neutral sources.
    - Discount or be skeptical of sources that show bias, sensationalism, or lack of supporting evidence.
    - Consider any contradictory or conflicting information.
    4. Be cautious of misinformation patterns, even if some claims appear plausible.

    Content to Evaluate (Claim or Tweet):
    \"{claim_text}\"

    Search Results Snippets:
    """
    for i, result in enumerate(search_results, 1):
        prompt += f"\n{i}. URL: {result.get('url', 'N/A')}\n   Title: {result.get('title', 'N/A')}\n   Snippet: {result.get('snippet', 'N/A')}\n"

    prompt += """
    Based on these snippets, provide:
    1. Whether the post contains one or more factual claims. If not, write "Inga verifierbara påståenden hittades."
    2. If claims exist:
    - A truthfulness rating for the overall claim(s) using the following categories:
        * Likely True
        * Likely False
        * Misleading
        * Uncertain
        * Cannot Verify
    - A brief reasoning (1-2 sentences) explaining your rating. Mention any contradictory information, detected bias, or low-reliability content you considered.
    - A numeric "Truthfulness Score" from 0 to 10 (where 0 = completely false or unreliable, 10 = clearly true based on strong evidence).

    Output format:
    Claim(s) Detected: [Summarize the identified factual claim(s), or write "Inga verifierbara påståenden hittades."]
    Rating: [Your chosen rating category]
    Reasoning: [Your brief explanation]
    Truthfulness Score: [0-10]
    """

    try:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = llm_model.generate_content(prompt, safety_settings=safety_settings)
        llm_output = response.text.strip()
        print(f"LLM Raw Output:\n{llm_output}")

        rating = "Error Parsing LLM Output"
        reasoning = "Could not parse the reasoning from the LLM response."
        truthfulness_score = None

        lines = llm_output.split('\n')
        for line in lines:
            if line.lower().startswith("rating:"):
                rating = line.split(":", 1)[1].strip()
            elif line.lower().startswith("reasoning:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line.lower().startswith("truthfulness score:"):
                truthfulness_score = line.split(":", 1)[1].strip()

        valid_ratings = ['Likely True', 'Likely False', 'Misleading', 'Uncertain', 'Cannot Verify', 'Error Parsing LLM Output']
        if rating not in valid_ratings:
             print(f"WARNING: LLM provided an unexpected rating category: {rating}. Storing as is.")

        print(f"Parsed Rating: {rating}")
        print(f"Parsed Reasoning: {reasoning}")
        print(f"Parsed Truthfulness Score: {truthfulness_score}")

        return {"rating": rating, "reasoning": reasoning, "truthfulness_score": truthfulness_score}
    except Exception as e:
        print(f"ERROR: LLM API call or parsing failed: {e}")
        try:
            print(f"LLM Prompt Feedback: {response.prompt_feedback}")
        except:
            pass
        return {"rating": "LLM Error", "reasoning": f"An error occurred during LLM evaluation: {e}", "truthfulness_score": None}
