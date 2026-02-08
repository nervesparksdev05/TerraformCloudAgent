# Langfuse Integration Guide

## ✅ Current Status: **Already Integrated!**

Langfuse is **fully integrated** into your Terraform Cloud Agent. It's currently **disabled** because the API keys are not configured, but all the code is in place and ready to use.

---

## 🎯 What Langfuse Provides

Langfuse is an **open-source LLM observability platform** that gives you:

1. **📊 Trace Visualization** - See every LLM call with inputs, outputs, and latency
2. **💰 Cost Tracking** - Monitor token usage and costs per request
3. **🐛 Debugging** - Inspect failed generations and error patterns
4. **📈 Analytics** - Track performance metrics over time
5. **🔍 Prompt Management** - Version and compare different prompts
6. **⚡ Performance Monitoring** - Identify slow requests and bottlenecks

---

## 🔧 Current Integration Points

### 1. Configuration (`app/core/config.py`)

```python
# Lines 25-29
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
ENABLE_TRACING = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)
```

**Tracing is automatically enabled** when both keys are present.

### 2. LLM Generator (`app/services/llm_generator.py`)

The `LLMGenerator` class has **4 Langfuse integration points**:

#### a) Main Generation Function (Line 43)
```python
@observe(name="generate_terraform")
def generate_terraform(self, request: str, provider: str = "aws") -> TerraformBundle:
```
- **Traces**: Every Terraform generation request
- **Captures**: Input request, provider, output bundle

#### b) Trace Metadata (Lines 58-62)
```python
if config.ENABLE_TRACING:
    langfuse_context.update_current_trace(
        tags=[provider, "terraform_generation"],
        input=request
    )
```
- **Tags**: Provider (aws/gcp) and operation type
- **Input**: User's natural language request

#### c) Fallback Tracking (Lines 77-80)
```python
if config.ENABLE_TRACING:
    langfuse_context.update_current_trace(
        metadata={"fallback_triggered": True, "primary_error": str(e)}
    )
```
- **Tracks**: When Gemini fallback is triggered
- **Captures**: Original OpenAI error

#### d) Gemini Fallback Function (Line 91)
```python
@observe(name="gemini_fallback")
def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
```
- **Traces**: Gemini API calls separately
- **Nested**: Under main `generate_terraform` trace

---

## 🚀 How to Enable Langfuse

### Step 1: Sign Up for Langfuse

1. Go to **https://cloud.langfuse.com** (free tier available)
2. Create an account
3. Create a new project (e.g., "Terraform Cloud Agent")

### Step 2: Get API Keys

1. In your Langfuse project, go to **Settings** → **API Keys**
2. Click **Create new API key**
3. Copy the **Public Key** (starts with `pk-lf-...`)
4. Copy the **Secret Key** (starts with `sk-lf-...`)

### Step 3: Configure Environment Variables

Add to your `.env` file:

```bash
# Langfuse (Tracing & Monitoring)
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key-here
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key-here
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Step 4: Restart Backend

```bash
# Stop the current server (Ctrl+C)
# Then restart:
uvicorn app.main:app --port 8001 --reload
```

### Step 5: Verify Integration

1. Make a Terraform generation request through your frontend
2. Go to **Langfuse Dashboard** → **Traces**
3. You should see a new trace with:
   - Name: `generate_terraform`
   - Tags: `aws` or `gcp`, `terraform_generation`
   - Input: Your natural language request
   - Output: Generated Terraform bundle

---

## 📊 What You'll See in Langfuse

### Trace Structure

```
generate_terraform (parent trace)
├── Input: "Deploy an EC2 instance with proper security groups..."
├── Tags: ["aws", "terraform_generation"]
├── Metadata: {provider: "aws", template_id: "aws_ec2_instance"}
├── Duration: 3.2s
├── Cost: $0.0045
└── Output: {main_tf: "...", variables_tf: "...", outputs_tf: "..."}
    └── gemini_fallback (child span, if triggered)
        ├── Metadata: {fallback_triggered: true, primary_error: "..."}
        ├── Duration: 2.1s
        └── Output: "..."
```

### Key Metrics You Can Track

1. **Success Rate**: % of successful generations
2. **Latency**: Average time per generation
3. **Cost**: Token usage and $ cost per request
4. **Fallback Rate**: How often Gemini is used
5. **Error Patterns**: Common failure modes
6. **Provider Distribution**: AWS vs GCP usage

---

## 🎨 Advanced: Custom Traces

You can add more observability by decorating other functions:

### Example: Track Security Validation

```python
# In app/services/security_checker.py
from langfuse.decorators import observe

class SecurityChecker:
    @classmethod
    @observe(name="security_validation")
    def validate(cls, bundle: TerraformBundle, provider: str) -> Tuple[bool, str]:
        # existing code...
```

### Example: Track Terraform Execution

```python
# In app/services/terraform_runner.py
from langfuse.decorators import observe

class TerraformRunner:
    @observe(name="terraform_pipeline")
    def run_pipeline(self, action: str = "apply") -> Tuple[bool, str, Optional[Dict], str]:
        # existing code...
```

---

## 💡 Best Practices

### 1. Tag Your Traces
```python
langfuse_context.update_current_trace(
    tags=["production", "aws", "ec2"],
    user_id=user_id,  # if you have user authentication
    session_id=session_id  # for grouping related requests
)
```

### 2. Add Metadata
```python
langfuse_context.update_current_trace(
    metadata={
        "template_id": "aws_ec2_instance",
        "region": "us-east-1",
        "instance_type": "t3.micro",
        "estimated_cost": "$0.01/hr"
    }
)
```

### 3. Track Scores
```python
# After user feedback
from langfuse import Langfuse
langfuse = Langfuse()
langfuse.score(
    trace_id=trace_id,
    name="user_satisfaction",
    value=5,  # 1-5 rating
    comment="User approved the generated code"
)
```

---

## 🔍 Debugging with Langfuse

### Common Scenarios

#### 1. High Latency
- **Dashboard**: Filter traces by duration > 5s
- **Identify**: Which provider/template is slow
- **Action**: Optimize prompts or switch models

#### 2. High Failure Rate
- **Dashboard**: Filter by status = error
- **Identify**: Common error patterns
- **Action**: Update prompts or add validation

#### 3. High Costs
- **Dashboard**: Sort by token usage
- **Identify**: Which requests use most tokens
- **Action**: Optimize prompts to reduce tokens

---

## 📈 Monitoring Dashboard Example

Once enabled, create a custom dashboard in Langfuse:

### Metrics to Track

1. **Request Volume** (requests/day)
2. **Success Rate** (% successful)
3. **P95 Latency** (95th percentile response time)
4. **Cost per Request** (average $ cost)
5. **Fallback Rate** (% using Gemini)
6. **Provider Distribution** (AWS vs GCP)
7. **Template Popularity** (most used templates)

---

## 🎯 Next Steps

1. **Sign up** for Langfuse (5 minutes)
2. **Add API keys** to `.env` (1 minute)
3. **Restart backend** (1 minute)
4. **Test a generation** (1 minute)
5. **View traces** in Langfuse dashboard (ongoing)

---

## 📚 Resources

- **Langfuse Docs**: https://langfuse.com/docs
- **Python SDK**: https://langfuse.com/docs/sdk/python
- **Decorators Guide**: https://langfuse.com/docs/sdk/python/decorators
- **Dashboard**: https://cloud.langfuse.com

---

## ✨ Summary

- ✅ **Langfuse is already integrated** - just needs API keys
- ✅ **Automatic tracing** of all LLM generations
- ✅ **Fallback tracking** when Gemini is used
- ✅ **Zero code changes needed** - just add environment variables
- ✅ **Free tier available** - perfect for development

**Ready to enable?** Just add your Langfuse API keys to `.env` and restart the backend!
