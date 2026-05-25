"""Speculative decoding for CodeLlama inference.

GAP-A6-004: implements the speculative decoding algorithm for use with
local model serving when latency SLAs are imposed.

Reference: Leviathan et al., "Fast Inference from Transformers via Speculative
Decoding", ICML 2023, arXiv:2211.17192.
Verified URL: https://arxiv.org/abs/2211.17192

Algorithm summary (Leviathan et al. §3):
  1. Draft model proposes K tokens autoregressively
  2. Target model verifies all K tokens in one forward pass (parallelism)
  3. Accept token i with probability min(1, p_target(i) / p_draft(i))
  4. On first rejection, resample from corrected distribution
  5. If all K accepted, sample one bonus token from target
  6. Repeat until max_new_tokens or EOS

Expected speedup: UNVERIFIED — Leviathan et al. report 2–3× on T5/GPT-2
families. CodeLlama-7B with CodeLlama-1.3B draft requires independent
measurement on target hardware before any latency claim is published.
"""
import torch
from transformers import PreTrainedModel, PreTrainedTokenizerBase


def speculative_generate(
    target_model: PreTrainedModel,
    draft_model: PreTrainedModel,
    tokenizer: PreTrainedTokenizerBase,
    input_ids: torch.Tensor,
    max_new_tokens: int = 128,
    draft_k: int = 4,
    temperature: float = 1.0,
) -> torch.Tensor:
    """Generate tokens using speculative decoding.

    Args:
        target_model: large verifier model (e.g. CodeLlama-7B)
        draft_model: small proposer model (e.g. CodeLlama-1.3B)
        tokenizer: shared tokenizer — vocab must be identical for both models
        input_ids: [1, seq_len] input token ids on the correct device
        max_new_tokens: maximum tokens to generate
        draft_k: candidate tokens proposed per iteration
        temperature: sampling temperature; 1.0 = no scaling

    Returns:
        output_ids: [1, seq_len + generated_len] including input tokens
    """
    eos_id = tokenizer.eos_token_id
    generated = input_ids.clone()

    for _ in range(max_new_tokens // draft_k + 1):
        if generated.shape[1] - input_ids.shape[1] >= max_new_tokens:
            break

        # Step 1: Draft model proposes K tokens autoregressively
        draft_tokens: list[torch.Tensor] = []
        draft_probs: list[float] = []
        draft_input = generated.clone()

        for _ in range(draft_k):
            with torch.no_grad():
                draft_out = draft_model(draft_input)
            logits = draft_out.logits[:, -1, :]
            if temperature != 1.0:
                logits = logits / temperature
            probs = torch.softmax(logits, dim=-1)
            next_tok = torch.multinomial(probs, num_samples=1)
            draft_tokens.append(next_tok)
            draft_probs.append(probs[0, next_tok.item()].item())
            draft_input = torch.cat([draft_input, next_tok], dim=-1)
            if next_tok.item() == eos_id:
                break

        # Step 2: Target model verifies all K draft tokens in one forward pass
        verify_input = torch.cat([generated] + draft_tokens, dim=-1)
        with torch.no_grad():
            target_out = target_model(verify_input)

        target_logits = target_out.logits[0, generated.shape[1] - 1 : -1, :]
        if temperature != 1.0:
            target_logits = target_logits / temperature
        target_probs = torch.softmax(target_logits, dim=-1)

        # Steps 3–4: Accept/reject with corrected resampling (Leviathan et al. Alg. 1)
        accepted = 0
        for i, (tok, q_i) in enumerate(zip(draft_tokens, draft_probs)):
            tok_id = tok.item()
            p_i = target_probs[i, tok_id].item()
            accept_prob = min(1.0, p_i / (q_i + 1e-9))
            if torch.rand(1).item() < accept_prob:
                generated = torch.cat([generated, tok], dim=-1)
                accepted += 1
                if tok_id == eos_id:
                    return generated
            else:
                # Resample from corrected distribution max(0, p_target - p_draft) / Z
                with torch.no_grad():
                    cur_target_logits = target_model(generated).logits[0, -1:, :]
                    if temperature != 1.0:
                        cur_target_logits = cur_target_logits / temperature
                    cur_target_probs = torch.softmax(cur_target_logits, dim=-1)[0]

                draft_probs_tensor = torch.softmax(
                    draft_model(generated).logits[0, -1:, :] / max(temperature, 1e-6),
                    dim=-1,
                )[0]
                correction = torch.clamp(cur_target_probs - draft_probs_tensor, min=0.0)
                norm = correction.sum()
                if norm > 1e-9:
                    resampled = torch.multinomial(
                        correction / norm, num_samples=1
                    ).unsqueeze(0)
                else:
                    resampled = torch.multinomial(
                        cur_target_probs, num_samples=1
                    ).unsqueeze(0)
                generated = torch.cat([generated, resampled], dim=-1)
                break  # stop at first rejection per algorithm

        # Step 5: If all K tokens accepted, sample one bonus token from target
        if accepted == len(draft_tokens):
            bonus_logits = target_out.logits[0, -1:, :]
            if temperature != 1.0:
                bonus_logits = bonus_logits / temperature
            bonus_probs = torch.softmax(bonus_logits, dim=-1)
            bonus_tok = torch.multinomial(bonus_probs, num_samples=1).unsqueeze(0)
            generated = torch.cat([generated, bonus_tok], dim=-1)
            if bonus_tok.item() == eos_id:
                break

    return generated
