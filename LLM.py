import google.generativeai as genai
import re # Import regex module for more robust parsing

def evaluate_claim_with_llm(claim_text, search_results, llm_model=genai.GenerativeModel(), metadata=None):
    """Uses Google Gemini to evaluate the claim based on search results. Optionally includes metadata (platform, post date) for context."""
    print(f"Evaluating claim using LLM: '{claim_text.split('#', 1)[0].strip()[:50]}...'")
    if not search_results:
        print("WARNING: No search results provided to LLM. Evaluation may be unreliable.")
        # Return the specific format even for no search results if the goal is consistency
        return {
            "rating": "Cannot Verify",
            "reasoning": "No search results available to verify the claim.",
            "truthfulness_score": None,
            "claims_detected": "Cannot Verify due to lack of search results."
        }

    # --- Add metadata context to the prompt if provided ---
    metadata_str = ""
    if metadata:
        platform = metadata.get('platform')
        post_date = metadata.get('post_date')
        if platform:
            metadata_str += f"\nPlatform: {platform}"
        if post_date:
            metadata_str += f"\nPost Date: {post_date}"
        if metadata_str:
            metadata_str = f"\n[Metadata]{metadata_str}\n"

    prompt = f"""
    Please act as a neutral and critical fact-checker. Your task is to evaluate the truthfulness of the following content, which may be a short social media post or tweet. The original post and search results may be in Swedish, and your output should also be in Swedish. Let's think step by step.

    {metadata_str if metadata_str else ''}
    Instructions:
    1.  **Crucially, first determine if the 'Content to Evaluate' contains one or more *specific, verifiable factual claims*.**
        * A factual claim is a statement asserting something that can potentially be proven true or false with objective evidence (e.g., data, statistics, historical records, scientific findings, quotes).
        * It is **NOT** an opinion (e.g., "this is good/bad"), a question, a prediction about the future, a command, a vague statement, or subjective experience.
        * **Example of a claim:** "Stockholm är Sveriges huvudstad." (Verifiable)
        * **Example of NOT a claim:** "Jag tycker att sommaren är bäst." (Opinion), "Kommer det att regna?" (Question), "Alla borde läsa mer." (Recommendation/Vague)
    2.  **If the content lacks *any* such verifiable factual claim:**
        * Your response for 'Claim(s) Detected:' MUST be exactly: Inga verifierbara påståenden hittades.
        * Your response for 'Rating:' MUST be exactly: Inga verifierbara påståenden hittades.
        * Your response for 'Reasoning:' should briefly state why no verifiable claim was found (e.g., "Innehållet uttrycker en åsikt." or "Innehållet ställer en fråga.").
        * Your response for 'Truthfulness Score:' should be N/A or left blank/null.
        * **Do NOT proceed to evaluate using search results if no verifiable claim is identified.**
    3.  **If, and *only* if, you identify one or more verifiable factual claims:**
        * Clearly state the identified claim(s) in the 'Claim(s) Detected:' field.
        * Evaluate their truthfulness based *only* on the provided search result snippets.
        * When reviewing the snippets:
            * Prioritize content from credible, authoritative, and neutral sources.
            * Discount or be skeptical of sources that show bias, sensationalism, or lack supporting evidence.
            * Consider any contradictory or conflicting information.
        * Be cautious of misinformation patterns.
        * Provide the appropriate rating, reasoning, and score based on your evaluation of the claim(s) against the evidence.

    Content to Evaluate (Claim or Tweet):
    \"{claim_text}\"

    Search Results Snippets:
    """
    for i, result in enumerate(search_results, 1):
        prompt += f"\n{i}. URL: {result.get('url', 'N/A')}\n   Title: {result.get('title', 'N/A')}\n   Snippet: {result.get('snippet', 'N/A')}\n"

    prompt += """
    Based *strictly* on the instructions above and the provided snippets, provide:

    Claim(s) Detected: [Summarize the identified factual claim(s), OR write *exactly* "Inga verifierbara påståenden hittades." if none were found.]
    Rating: [Your chosen rating category (Likely True, Likely False, Misleading, Uncertain, Cannot Verify) OR *exactly* "Inga verifierbara påståenden hittades." if no claim was detected.]
    Reasoning: [Your brief explanation based on the evaluation OR why no claim was found.]
    Truthfulness Score: [0-10 OR N/A if no claim was detected.]
    """

    try:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        # Consider adjusting generation config if needed, e.g., temperature for consistency
        # generation_config = genai.types.GenerationConfig(temperature=0.2)
        # response = llm_model.generate_content(prompt, safety_settings=safety_settings, generation_config=generation_config)
        response = llm_model.generate_content(prompt, safety_settings=safety_settings)
        llm_output = response.text.strip()
        print(f"LLM Raw Output:\n{llm_output}")

        # --- Improved Parsing Logic ---
        rating = "Error Parsing LLM Output"
        reasoning = "Could not parse the reasoning from the LLM response."
        truthfulness_score_str = None # Store as string initially
        claims_detected = "Error Parsing LLM Output"

        # Use regex for more flexible matching, ignoring case and surrounding whitespace
        claims_match = re.search(r"Claim\(s\) Detected:\s*(.*)", llm_output, re.IGNORECASE | re.DOTALL)
        rating_match = re.search(r"Rating:\s*(.*)", llm_output, re.IGNORECASE | re.DOTALL)
        reasoning_match = re.search(r"Reasoning:\s*(.*)", llm_output, re.IGNORECASE | re.DOTALL)
        score_match = re.search(r"Truthfulness Score:\s*(.*)", llm_output, re.IGNORECASE | re.DOTALL)

        # Extract matched groups, cleaning up potential trailing fields
        if claims_match:
            claims_detected = claims_match.group(1).split('\n')[0].strip()
        if rating_match:
            rating = rating_match.group(1).split('\n')[0].strip()
        if reasoning_match:
            reasoning = reasoning_match.group(1).split('\n')[0].strip()
        if score_match:
            truthfulness_score_str = score_match.group(1).split('\n')[0].strip()

        # --- Post-processing Check for "No Verifiable Claims" ---
        # Standardize the target phrase
        no_claims_phrase = "Inga verifierbara påståenden hittades"
        is_no_claim_case = False

        # Check if the LLM explicitly used the required phrase in key fields
        if claims_detected.strip().lower() == no_claims_phrase.lower() or \
           rating.strip().lower() == no_claims_phrase.lower():
            is_no_claim_case = True
            print("LLM indicated no verifiable claims found via specific phrase.")
            rating = no_claims_phrase # Ensure the rating is exactly this
            claims_detected = no_claims_phrase # Ensure claims detected is exactly this

        # Fallback: Check reasoning or score for indicators if the primary fields missed it
        # (Less strict than before, prioritizes the explicit instruction)
        no_claim_indicators_in_reasoning = [
            "inga verifierbara påståenden", "ingen verifierbar", "inga påståenden",
            "inga faktapåståenden", "innehåller inte något påstående",
            "innehåller inte några påståenden", "är en åsikt", "ställer en fråga",
            "är en uppmaning", "är subjektivt", "no verifiable claims",
            "no factual claims", "is an opinion", "asks a question"
        ]
        if not is_no_claim_case and reasoning and any(phrase in reasoning.lower() for phrase in no_claim_indicators_in_reasoning):
             # Check if rating is also non-committal (e.g. Uncertain/Cannot Verify) before overriding
             if rating in ["Uncertain", "Cannot Verify", "Error Parsing LLM Output"]:
                 print("LLM reasoning suggests no verifiable claims found, overriding rating.")
                 is_no_claim_case = True
                 rating = no_claims_phrase
                 claims_detected = no_claims_phrase # Standardize output

        # Finalize score based on whether it's a 'no claim' case
        truthfulness_score = None
        if not is_no_claim_case and truthfulness_score_str:
             # Try converting score to number only if claims were found
             try:
                 # Handle potential ranges or non-numeric values gracefully
                 score_cleaned = re.match(r"^\s*(\d{1,2}(?:\.\d+)?)\s*", truthfulness_score_str) # Match 0-10 possibly with decimal
                 if score_cleaned:
                     truthfulness_score = float(score_cleaned.group(1))
                     if 0 <= truthfulness_score <= 10:
                         truthfulness_score = int(truthfulness_score) if truthfulness_score.is_integer() else truthfulness_score
                     else:
                         print(f"WARNING: Parsed score {truthfulness_score} out of range 0-10.")
                         truthfulness_score = None # Or clamp it? Set to None for now.
                 elif truthfulness_score_str.strip().upper() == 'N/A':
                     truthfulness_score = None
                 else:
                    print(f"WARNING: Could not parse numeric score from '{truthfulness_score_str}'")
                    truthfulness_score = None
             except ValueError:
                 print(f"WARNING: Could not parse truthfulness score '{truthfulness_score_str}' as a number.")
                 truthfulness_score = None
        elif is_no_claim_case:
             truthfulness_score = None # Ensure score is None if no claims

        # Validate Rating
        valid_ratings = ['Likely True', 'Likely False', 'Misleading', 'Uncertain', 'Cannot Verify', no_claims_phrase, 'Error Parsing LLM Output']
        if rating not in valid_ratings:
              print(f"WARNING: LLM provided an unexpected rating category: '{rating}'. Storing as is, but might indicate misinterpretation.")
              # Optionally force a default like 'Uncertain' or keep the unexpected value
              # rating = "Uncertain"


        print(f"Parsed Claims Detected: {claims_detected}")
        print(f"Parsed Rating: {rating}")
        print(f"Parsed Reasoning: {reasoning}")
        print(f"Parsed Truthfulness Score: {truthfulness_score}")

        return {"rating": rating, "reasoning": reasoning, "truthfulness_score": truthfulness_score, "claims_detected": claims_detected}

    except Exception as e:
        print(f"ERROR: LLM API call or parsing failed: {e}")
        try:
            # Log feedback if available, helps debug BLOCKING issues
            print(f"LLM Prompt Feedback: {response.prompt_feedback}")
            if response.prompt_feedback.block_reason:
                 print(f"Content blocked due to: {response.prompt_feedback.block_reason}")
        except Exception as feedback_error:
             print(f"Could not retrieve prompt feedback: {feedback_error}")
        return {"rating": "LLM Error", "reasoning": f"An error occurred during LLM evaluation: {e}", "truthfulness_score": None, "claims_detected": "LLM Error"}