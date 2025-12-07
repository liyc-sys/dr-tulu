# 添加的API转发设置
export http_proxy="http://httpproxy.glm.ai:8888"
export https_proxy="http://httpproxy.glm.ai:8888"
export no_proxy="127.0.0.1,localhost,platform.glm.ai,::1,$no_proxy"

export OPENAI_API_KEY="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"
export OPENAI_API_BASE="https://openrouter.ai/api/v1"

# 添加工具API KEY
export S2_API_KEY=sk-user-F788DB8EABBDAD1858E82734A4E0C1BA
export SERPER_API_KEY=56e20b0fb1dc8a9d19fb80be90fb346e63294148

# 注意
# Configuration: GPU setup
# 可用环境变量：
#   NUM_GPUS            覆盖总体 GPU 规模提示（默认 4）
#   NUM_LEARNERS        learner 进程数量（默认 4）
#   VLLM_ENGINES        vLLM 引擎数量（默认 4）
#   单卡调试：export NUM_GPUS=1 或 NUM_GPUS=single
NUM_GPUS=${NUM_GPUS:-4}                # 默认用 4（适配 8 卡机器：4 learner + 4 vLLM）
NUM_LEARNERS=${NUM_LEARNERS:-4}        # learner 数；与 NUM_GPUS 解耦，便于控制总需求
VLLM_ENGINES=${VLLM_ENGINES:-4}        # vLLM 引擎数；与 learner 分开控制
SINGLE_GPU_MODE=false
if [ "$NUM_GPUS" == "1" ] || [ "$NUM_GPUS" == "single" ]; then
    SINGLE_GPU_MODE=true
    NUM_LEARNERS=1
    VLLM_ENGINES=1
    VLLM_GPU_MEMORY_UTIL=0.3
    VLLM_SYNC_BACKEND="gloo"
else
    VLLM_GPU_MEMORY_UTIL=""
    VLLM_SYNC_BACKEND=""
fi

model_path=/workspace/math_science_data/lyc/models/DR-Tulu-SFT-8B
dataset_list="rl-research/dr-tulu-rl-data 1.0"
exp_name="dr-tulu-dora"
log_file="train_${exp_name}_$(date +%Y%m%d_%H%M%S).log"

echo "日志文件将保存到: ${log_file}"
echo "开始使用 DoRA 训练..."

# set env vars
export WANDB_API_KEY=66b0b8398e5e095610d55373d3f5eff647e58405
export CRAWL4AI_BLOCKLIST_PATH=/stage/rl-rag-mcp/utils/crawl4ai_block_list.txt
export MCP_MAX_CONCURRENT_CALLS=512
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export RUBRIC_JUDGE_MODEL=gpt-4.1-mini
export MCP_CACHE_DIR=.cache-${RANDOM}
export MCP_TRANSPORT_PORT=8003

# Build additional arguments based on GPU configuration
ADDITIONAL_ARGS=""
if [ "$SINGLE_GPU_MODE" == "true" ]; then
    ADDITIONAL_ARGS="--single_gpu_mode True --vllm_gpu_memory_utilization ${VLLM_GPU_MEMORY_UTIL} --vllm_sync_backend ${VLLM_SYNC_BACKEND}"
fi

uv run --extra compile python open_instruct/grpo_fast.py \
        --exp_name ${exp_name} \
        --wandb_project_name rl-rag \
        --beta 0.001 \
        --num_samples_per_prompt_rollout 8 \
        --num_unique_prompts_rollout 32 \
        --num_mini_batches 1 \
        --num_epochs 1 \
        --learning_rate 5e-7 \
        --per_device_train_batch_size 1 \
        --output_dir output \
        --kl_estimator kl3 \
        --dataset_mixer_list ${dataset_list} \
        --dataset_mixer_list_splits train \
        --dataset_mixer_eval_list rl-research/dr-tulu-rl-data 16 \
        --dataset_mixer_eval_list_splits train \
        --apply_adaptive_rubric_reward true \
        --normalize_rubric_scores false \
        --use_rubric_buffer true \
        --use_static_rubrics_as_persistent_rubrics true \
        --max_active_rubrics 5 \
        --max_token_length 10240 \
        --max_prompt_token_length 2048 \
        --response_length 16384 \
        --pack_length 18500 \
        --model_name_or_path ${model_path} \
        --non_stop_penalty False \
        --non_stop_penalty_value 0.0 \
        --temperature 1.0 \
        --ground_truths_key ground_truth \
        --sft_messages_key messages \
        --total_episodes 10000000 \
        --deepspeed_stage 3 \
        --num_learners_per_node ${NUM_LEARNERS} \
        --vllm_num_engines ${VLLM_ENGINES} \
        --vllm_tensor_parallel_size 1 \
        --lr_scheduler_type constant \
        --apply_verifiable_reward true \
        --seed 1 \
        --num_evals 500 \
        --save_freq 50 \
        --try_launch_beaker_eval_jobs_on_weka False \
        --gradient_checkpointing \
        --with_tracking \
        --max_tool_calls 10 \
        --only_reward_good_outputs False \
        --tools mcp \
        --checkpoint_state_freq 50 \
        --checkpoint_state_dir output/checkpoints \
        --mcp_parser_name v20250824 \
        --system_prompt_file open_instruct/search_utils/system_prompts/unified_tool_calling_v20250907.yaml  \
        --mcp_tool_names 'snippet_search,google_search,browse_webpage' \
        --mcp_server_command "uv run python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp" \
        --use_peft \
        --use_dora \
        --lora_r 16 \
        --lora_alpha 32 \
        --lora_dropout 0.05 \
        ${ADDITIONAL_ARGS} 2>&1 | tee ${log_file}

echo "训练完成！使用 DoRA 的 adapter 权重已保存。"
echo "如需合并 adapter 到基础模型，请使用 merge_lora.py 脚本。"

