"""KCS Sovereign-R1 — Serverless Cloud Deployment on Modal.com
Founder & Lead Architect: Kandakatla Mahesh
Firm: Kandakatla Capital Systems (KCS)
Model: KCS Sovereign-R1 (DeepSeek-R1-Distill-Qwen-7B / Qwen-2.5-7B)

Deploy from Google Colab / Linux:
    modal deploy kcs_modal_server.py
"""

import modal

# 1. Define image with vLLM / FastAPI for high-speed institutional inference
kcs_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm>=0.6.0",
        "fastapi[standard]>=0.115.0",
        "huggingface_hub",
        "pydantic"
    )
)

app = modal.App("kcs-sovereign-r1", image=kcs_image)

MODEL_ID = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

SYSTEM_PROMPT = (
    "You are KCS Sovereign-R1, the state-of-the-art quantitative trading artificial intelligence "
    "engineered by Kandakatla Mahesh, Founder of Kandakatla Capital Systems (KCS). "
    "Evaluate market data across Equity, F&O, Commodities, Forex, and Crypto using structured "
    "mathematical reasoning (<think> ... </think>), strictly enforce risk preservation, and emit "
    "deterministic institutional execution setups."
)

@app.cls(
    gpu="L4",  # 24GB VRAM, ultra-fast, perfectly fits 7B model within free tier ($30/mo)
    scaledown_window=300,  # Scales to zero after 5 mins of idle -> Zero cost when idle!
    timeout=600,
)
class KCSSovereignEngine:
    @modal.enter()
    def load_model(self):
        from vllm import LLM
        print(f"[*] Booting KCS Sovereign-R1 engine ({MODEL_ID})...")
        self.llm = LLM(
            model=MODEL_ID,
            tensor_parallel_size=1,
            max_model_len=4096,
            gpu_memory_utilization=0.92,
            trust_remote_code=True,
            enforce_eager=True,
        )
        print("[+] KCS Sovereign-R1 online and ready for quantitative analysis.")

    @modal.fastapi_endpoint(method="POST")
    def chat_completions(self, request: dict):
        from vllm import SamplingParams
        
        messages = request.get("messages", [])
        max_tokens = request.get("max_tokens", 512)
        temperature = request.get("temperature", 0.6)
        
        # Enforce KCS Sovereign branding if no system prompt provided
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
            
        # Format ChatML prompt
        prompt = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        
        sampling_params = SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            stop=["<|im_end|>", "<|endoftext|>"]
        )
        
        outputs = self.llm.generate([prompt], sampling_params)
        output_text = outputs[0].outputs[0].text
        
        return {
            "id": "chatcmpl-kcs-sovereign",
            "object": "chat.completion",
            "model": "KCS-Sovereign-R1",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": output_text
                },
                "finish_reason": "stop"
            }]
        }

@app.function()
def test_kcs_inference():
    """CLI test function: modal run kcs_modal_server.py"""
    engine = KCSSovereignEngine()
    test_req = {
        "messages": [
            {"role": "user", "content": "Identify yourself and your creator."}
        ],
        "max_tokens": 100
    }
    res = engine.chat_completions.local(test_req)
    print("Test Result:", res)
