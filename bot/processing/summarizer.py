import torch
import json
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from utils.logger import logger
from bot.utils import config
from bot.processing.prompt_generator import generate_prompt_2

# Use model from config
MODEL_ID = config.LLM_MODEL

def get_model_loading_config():
    """Determine best model and loading settings based on hardware specs"""
    global MODEL_ID
    
    if not torch.cuda.is_available():
        logger.warning("No CUDA device detected. Falling back to CPU and Qwen2.5-7B (4bit).")
        if MODEL_ID == "auto":
            MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
        return {
            "device_map": "cpu",
            "torch_dtype": torch.float32
        }
    
    # Check VRAM in GB
    total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    logger.info(f"Detected GPU with {total_vram:.2f} GB VRAM")
    
    # Auto-selection logic
    if MODEL_ID == "auto":
        if total_vram >= 12:
            MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
            logger.info("High-end GPU detected. Auto-selecting LLaMA-3.1-8B.")
        else:
            MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
            logger.info("Lower VRAM GPU detected. Auto-selecting Qwen2.5-7B.")

    # High-end GPU (>= 16GB VRAM) - Full precision for 7B/8B
    if total_vram >= 16 and "14B" not in MODEL_ID:
        logger.info(f"Sufficient VRAM for {MODEL_ID}. Using full precision (float16/bfloat16).")
        return {
            "device_map": "auto",
            "torch_dtype": torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        }
    # Mid-range/Low-end or Large Models
    else:
        logger.info(f"Using INT4 quantization for {MODEL_ID} for memory efficiency.")
        return {
            "device_map": "auto",
            "load_in_4bit": True,
            "torch_dtype": torch.float16,
            "bnb_4bit_compute_dtype": torch.float16,
            "bnb_4bit_quant_type": "nf4",
            "bnb_4bit_use_double_quant": True,
        }

def run_llm_processing(session_dir):
    session_path = Path(session_dir)
    prompt1_path = session_path / "PROMPT1"
    
    if not prompt1_path.exists():
        logger.error(f"PROMPT1 not found at {prompt1_path}. Cannot start LLM processing.")
        return

    logger.info(f"Starting LLM processing for session: {session_dir}")
    
    # 1. Load Model and Tokenizer
    loading_kwargs = get_model_loading_config()
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            **loading_kwargs
        )
        
        # 2. Run Step 1: Data Extraction (PROMPT1)
        with open(prompt1_path, "r", encoding="utf-8") as f:
            prompt1_content = f.read()
            
        logger.info("Running Step 1: Fact Extraction...")
        extracted_json_text = generate_response(model, tokenizer, prompt1_content)
        
        # Clean up JSON (sometimes models add markdown triple backticks)
        if "```json" in extracted_json_text:
            extracted_json_text = extracted_json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in extracted_json_text:
            extracted_json_text = extracted_json_text.split("```")[1].split("```")[0].strip()
            
        # Save extracted data
        json_output_path = session_path / "extracted_data.json"
        try:
            # Validate JSON
            json_data = json.loads(extracted_json_text)
            with open(json_output_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=4)
            logger.info(f"Step 1 complete. Extracted data saved to {json_output_path}")
        except Exception as e:
            logger.error(f"Failed to parse LLM output as JSON: {e}")
            logger.debug(f"Raw output: {extracted_json_text}")
            # Save raw if it fails for debugging
            with open(session_path / "extracted_data_raw.txt", "w", encoding="utf-8") as f:
                f.write(extracted_json_text)
            return

        # 3. Run Step 2: Minutes Generation (PROMPT2)
        generate_prompt_2(session_dir)
        prompt2_path = session_path / "PROMPT2"
        
        if prompt2_path.exists():
            with open(prompt2_path, "r", encoding="utf-8") as f:
                prompt2_content = f.read()
                
            logger.info("Running Step 2: Meeting Minutes Synthesis...")
            minutes_markdown = generate_response(model, tokenizer, prompt2_content)
            
            # Save final report
            minutes_path = session_path / "Meeting_Minutes.md"
            with open(minutes_path, "w", encoding="utf-8") as f:
                f.write(minutes_markdown)
            logger.info(f"Step 2 complete. Minutes saved to {minutes_path}")
            
    except Exception as e:
        logger.error(f"Error during LLM processing: {e}")
    finally:
        # Clean up GPU memory
        if 'model' in locals():
            del model
        if 'tokenizer' in locals():
            del tokenizer
        torch.cuda.empty_cache()
        logger.info("LLM processing finished and resources cleared.")

def generate_response(model, tokenizer, full_prompt):
    """Helper to generate response from model"""
    # Qwen-specific chat format handling
    messages = [
        {"role": "user", "content": full_prompt}
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=2048,
        temperature=0.7,
        top_p=0.9,
        do_sample=True
    )
    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]

    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    return response.strip()
