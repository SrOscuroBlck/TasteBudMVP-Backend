# LLM Model Configuration

This document describes the Large Language Model configuration for the TasteBud recommendation system.

## Current Models (January 2026)

### Primary Model: GPT-5 Nano

**Model ID:** `gpt-5-nano`

**Use Cases:**
- Recommendation explanations
- Onboarding question generation
- Rationale generation
- Ingredient inference
- Profile summarization
- Reranking assistance

**Specifications:**
- **Context Window:** 400,000 tokens
- **Max Output:** 128,000 tokens
- **Knowledge Cutoff:** May 31, 2024
- **Reasoning:** Average
- **Speed:** Very fast
- **Supported Modalities:** Text input/output, Image input

**Pricing (Per 1M Tokens):**
- Input: $0.05
- Cached Input: $0.005
- Output: $0.40

**Rate Limits (Tier 1):**
- Requests per minute: 500
- Tokens per minute: 200,000
- Batch queue limit: 2,000,000

**Why GPT-5 Nano:**
- Fastest and most cost-efficient GPT-5 variant
- Excellent for summarization and classification tasks
- 8x cheaper on input vs GPT-4.1 nano ($0.05 vs $0.40)
- Same output cost as alternatives ($0.40)
- Perfect for high-volume tasks like explanation generation

---

### Fallback Model: GPT-4.1 Nano

**Model ID:** `gpt-4.1-nano`

**Use Cases:**
- Fallback when GPT-5 unavailable
- Tasks requiring stronger instruction following
- Complex tool calling scenarios

**Specifications:**
- **Context Window:** 1,047,576 tokens (1M+)
- **Max Output:** 32,768 tokens
- **Knowledge Cutoff:** June 01, 2024
- **Intelligence:** Average
- **Speed:** Very fast
- **Supported Modalities:** Text input/output, Image input

**Pricing (Per 1M Tokens):**
- Input: $0.10
- Cached Input: $0.025
- Output: $0.40

**Rate Limits (Tier 1):**
- Requests per minute: 500
- Requests per day: 10,000
- Tokens per minute: 200,000
- Batch queue limit: 2,000,000

**When to Use GPT-4.1 Nano:**
- GPT-5 service unavailable
- Tasks requiring longer context (>400K tokens)
- Scenarios where instruction following is critical
- Fine-tuned model variants (GPT-4.1 supports fine-tuning)

---

## Configuration

### Environment Variables

Set the model in your `.env` file:

```bash
OPENAI_MODEL=gpt-5-nano
```

Or use the fallback:

```bash
OPENAI_MODEL=gpt-4.1-nano
```

### Code Usage

All services use the configured model via `settings.OPENAI_MODEL`:

```python
from config.settings import settings
from openai import OpenAI

client = OpenAI(api_key=settings.OPENAI_API_KEY)

response = client.chat.completions.create(
    model=settings.OPENAI_MODEL,  # Uses gpt-5-nano by default
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)
```

---

## Cost Analysis

### GPT-5 Nano Cost Examples

**Explanation Generation (100 tokens input, 50 tokens output per explanation):**
- Input: 0.0001M × $0.05 = $0.000005
- Output: 0.00005M × $0.40 = $0.00002
- **Total per explanation: $0.000025**
- **10,000 explanations: $0.25**

**Onboarding Question (200 tokens input, 250 tokens output):**
- Input: 0.0002M × $0.05 = $0.00001
- Output: 0.00025M × $0.40 = $0.0001
- **Total per question: $0.00011**
- **10,000 questions: $1.10**

### Cost Comparison

| Model | Input (1M tokens) | Output (1M tokens) | Total (1M in + 1M out) |
|-------|-------------------|--------------------|-----------------------|
| GPT-5 nano | $0.05 | $0.40 | $0.45 |
| GPT-4.1 nano | $0.10 | $0.40 | $0.50 |
| GPT-4.1 mini | $0.40 | $0.40 | $0.80 |

**Savings:**
- GPT-5 nano vs GPT-4.1 nano: 10% total cost reduction (50% on input)
- GPT-5 nano vs GPT-4.1 mini: 44% total cost reduction

---

## Best Practices

### Optimize for Cost

1. **Use Cached Inputs** - Structure prompts to reuse system messages
2. **Batch Processing** - Generate multiple explanations in one call when possible
3. **Template First** - Use templates for common patterns, LLM for unique cases
4. **Appropriate Token Limits** - Set `max_tokens` to minimum needed

### Optimize for Performance

1. **Streaming** - Use streaming for user-facing responses
2. **Parallel Calls** - Generate explanations in parallel when order doesn't matter
3. **Fallback Strategy** - Gracefully degrade to simpler methods if LLM unavailable

### Optimize for Quality

1. **Temperature Settings:**
   - 0.5-0.6 for explanations (balance creativity and consistency)
   - 0.3-0.4 for structured outputs (JSON, classifications)
   - 0.7-0.8 for creative tasks (question generation)

2. **Prompt Engineering:**
   - Clear, concise system messages
   - Specific output format instructions
   - Include relevant context only

3. **Validation:**
   - Always validate JSON responses
   - Provide fallback values for malformed outputs
   - Log failures for monitoring

---

## Migration Notes

### From GPT-4o-mini (Previous Configuration)

**Breaking Changes:** None - API interface is identical

**Configuration Changes:**
- Updated `config/settings.py` default from `gpt-4o-mini` to `gpt-5-nano`
- Updated `.env.example` and `.env` files
- Updated `docker-compose.yml` environment variable default

**Benefits:**
- Lower costs on input tokens (50% reduction vs GPT-4.1 nano)
- Same quality for summarization and classification tasks
- Faster response times
- Larger context window (400K vs typical)

**Migration Date:** January 4, 2026

---

## Monitoring

### Track These Metrics

1. **Token Usage:**
   - Input tokens per request
   - Output tokens per request
   - Cached token usage

2. **Costs:**
   - Daily API spend
   - Cost per recommendation
   - Cost per user interaction

3. **Performance:**
   - API latency (p50, p95, p99)
   - Success rate
   - Fallback usage frequency

4. **Quality:**
   - Explanation relevance (user feedback)
   - JSON parsing success rate
   - Hallucination frequency

### OpenAI Dashboard

Monitor usage at: https://platform.openai.com/usage

---

## Future Considerations

### When to Upgrade

Consider upgrading to a more powerful model if:
- Tasks require deeper reasoning (GPT-5 standard)
- Context exceeds 400K tokens regularly (GPT-4.1 nano has 1M+)
- Quality issues observed with current model
- Budget allows for higher accuracy needs

### Multi-Model Strategy

Future phases may implement:
- GPT-5 nano for explanations, questions, simple tasks
- GPT-5 standard for complex reranking and profile summarization
- GPT-4.1 nano as universal fallback
- Local models for privacy-sensitive operations

### Cost Optimization Roadmap

Phase 5 will introduce:
- Redis caching for common explanations
- Template coverage >80% (reduce LLM calls)
- Batch API for non-real-time tasks (50% cost reduction)
- Prompt compression techniques
