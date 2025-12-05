# RL训练流程详解

本文档详细说明了DR-Tulu项目中RL（强化学习）训练的整体流程，主要基于PPO和GRPO算法。

## 一、训练入口

### 1.1 主入口函数
训练从 `main()` 函数开始，位于：
- **PPO训练**: `ppo_vllm_thread_ray_gtrl.py`
- **GRPO训练**: `grpo_vllm_thread_ray_gtrl.py`

### 1.2 启动脚本
通过 `train_dr_tulu.sh` 启动训练，主要参数包括：
- 模型路径、数据集配置
- DeepSpeed配置（stage 3）
- vLLM引擎配置
- 奖励函数配置

## 二、初始化阶段

### 2.1 基础设置
```1714:1731:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
def main(args: Args, tc: TokenizerConfig, model_config: ModelConfig):
    # ------------------------------------------------------------
    # Setup tokenizer
    tc.tokenizer_revision = model_config.model_revision if tc.tokenizer_revision is None else tc.tokenizer_revision
    tc.tokenizer_name_or_path = (
        model_config.model_name_or_path if tc.tokenizer_name_or_path is None else tc.tokenizer_name_or_path
    )
    if (
        tc.tokenizer_revision != model_config.model_revision
        and tc.tokenizer_name_or_path != model_config.model_name_or_path
    ):
        # Warn user if tokenizer and model use different revisions; this is an unusual
        # use case.
        warning = f"""Requested tokenizer revision `{tc.tokenizer_revision=}` is different
                   from the model revision `{model_config.model_revision=}` or the tokenizer name `{tc.tokenizer_name_or_path=}`
                   is different from the model name `{model_config.model_name_or_path=}`."""
        print(warning)
    tokenizer = tc.tokenizer
```

### 2.2 数据集加载
```1800:1836:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
    # ------------------------------------------------------------
    # Set up datasets
    transform_fn_args = [
        {},
        {
            "max_token_length": args.max_token_length,
            "max_prompt_token_length": args.max_prompt_token_length,
        },
    ]
    train_dataset = get_cached_dataset_tulu(
        dataset_mixer_list=args.dataset_mixer_list,
        dataset_mixer_list_splits=args.dataset_mixer_list_splits,
        tc=tc,
        dataset_transform_fn=args.dataset_transform_fn,
        transform_fn_args=transform_fn_args,
        dataset_cache_mode=args.dataset_cache_mode,
        dataset_config_hash=args.dataset_config_hash,
        hf_entity=args.hf_entity,
        dataset_local_cache_dir=args.dataset_local_cache_dir,
        dataset_skip_cache=args.dataset_skip_cache,
    )
    train_dataset = train_dataset.shuffle(seed=args.seed)
    eval_dataset = None
    if len(args.dataset_mixer_eval_list) > 0:
        eval_dataset = get_cached_dataset_tulu(
            args.dataset_mixer_eval_list,
            args.dataset_mixer_eval_list_splits,
            tc,
            args.dataset_transform_fn,
            transform_fn_args,
            hf_entity=args.hf_entity,
            dataset_cache_mode=args.dataset_cache_mode,
            dataset_config_hash=args.dataset_config_eval_hash,
            dataset_local_cache_dir=args.dataset_local_cache_dir,
            dataset_skip_cache=args.dataset_skip_cache,
        )
        eval_dataset = eval_dataset.shuffle(seed=args.seed)
```

### 2.3 模型和引擎初始化
```1846:1881:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
    # create the model and optimizer
    pg = None
    bundles = [{"GPU": actor_num_gpus, "CPU": actor_num_gpus * 10} for actor_num_gpus in args.actor_num_gpus_per_node]
    pg = placement_group(bundles, strategy="STRICT_SPREAD")
    ray.get(pg.ready())

    inits = []
    policy_group = ModelGroup(
        pg,
        PolicyTrainerRayProcess,
        args.actor_num_gpus_per_node,
        args.single_gpu_mode,
    )
    wandb_url = wandb.run.get_url() if args.with_tracking else None
    inits.extend(
        model.from_pretrained.remote(args, model_config, beaker_config, wandb_url) for model in policy_group.models
    )
    max_len = args.max_prompt_token_length + args.response_length
    vllm_engines = create_vllm_engines(
        args.vllm_num_engines,
        args.vllm_tensor_parallel_size,
        args.vllm_enforce_eager,
        tc.tokenizer_name_or_path,
        model_config.model_name_or_path,
        model_config.model_revision,
        args.seed,
        args.enable_prefix_caching,
        max_len,
        args.vllm_gpu_memory_utilization,
        args.single_gpu_mode,
        pg=pg if args.single_gpu_mode else None,
    )

    metrics_queue = RayQueue()
    ray.get(inits)
    print("======== all models initialized =========")
```

### 2.4 启动训练进程
```1883:1894:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
    refs = []
    for i, policy_model in enumerate(policy_group.models):
        refs.append(
            policy_model.train.remote(
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                tokenizer=tokenizer,
                vllm_engines=vllm_engines,
                metrics_queue=metrics_queue,
                data_collator=data_collator,
            )
        )
```

## 三、训练循环（每个训练步骤）

训练循环在 `PolicyTrainerRayProcess.train()` 方法中执行，主要包含以下阶段：

### 3.1 Rollout阶段：生成响应

#### 3.1.1 异步生成线程
使用vLLM引擎在独立线程中异步生成响应：

```1034:1080:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
        def vllm_generate(
            generation_config: SamplingParams,
            response_ids_Q: Queue,
            param_prompt_Q: Queue,
            num_training_steps: int,
            sample_evaluation_prompt_token_ids: Optional[List[int]],
            evaluation_Q: Queue,
            eval_freq: int,
            resume_training_step: int,
        ):
            def generate_with_engines(prompts: List[List[int]], sampling_params: SamplingParams):
                # Split queries between engines
                queries_per_engine = math.ceil(len(prompts) / len(vllm_engines))
                split_queries = [
                    prompts[i : i + queries_per_engine] for i in range(0, len(prompts), queries_per_engine)
                ]
                # Generate responses in parallel across engines
                futures = [
                    vllm_engine.generate.remote(
                        sampling_params=sampling_params, prompt_token_ids=queries, use_tqdm=False
                    )
                    for vllm_engine, queries in zip(vllm_engines, split_queries)
                ]
                # Gather all responses
                all_outputs = ray.get(futures)
                response_ids = []
                for outputs in all_outputs:
                    response_ids.extend([list(out.token_ids) for output in outputs for out in output.outputs])
                return response_ids

            for training_step in range(resume_training_step, num_training_steps + 1):
                items = param_prompt_Q.get()
                if items is None:
                    break
                _, g_queries_list = items

                with Timer("🔥🔥🔥 Generation time", noop=self.rank != 0):
                    response_ids = generate_with_engines(g_queries_list, generation_config)
                response_ids_Q.put(response_ids)

                # Evaluate the model
                if sample_evaluation_prompt_token_ids is not None and (training_step - 1) % eval_freq == 0:
                    response_ids = generate_with_engines(
                        sample_evaluation_prompt_token_ids, evaluation_generation_config
                    )
                    evaluation_Q.put(response_ids)
```

#### 3.1.2 获取生成的响应
```1219:1234:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
                if self.rank == 0:
                    g_response_token_ids = response_ids_Q.get()
                    DUMMY_PAD_TOKEN = (
                        args.stop_token_id
                    )  # we can't use tokenizer.pad_token_id because it's outside vocab and `torch.gather(all_logprob, 2, response.unsqueeze(-1))` will error out
                    g_padded_response_ids = [
                        response + [DUMMY_PAD_TOKEN] * (args.response_length - len(response))
                        for response in g_response_token_ids
                    ]
                    g_padded_response_ids = torch.tensor(g_padded_response_ids, device=device)
                    g_vllm_responses[:] = g_padded_response_ids
                dist.broadcast(g_vllm_responses, src=0)
                local_vllm_responses = g_vllm_responses[
                    accelerator.process_index * queries.shape[0] : (accelerator.process_index + 1) * queries.shape[0]
                ]
                query_responses = torch.cat((queries, local_vllm_responses), 1)
```

### 3.2 奖励计算阶段

#### 3.2.1 计算策略和参考模型的logprobs
```1246:1261:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
                    # Get policy model logprob
                    logprob = self.forward(
                        self.model, query_response, response, tokenizer.pad_token_id, context_length, args.temperature
                    )
                    torch.cuda.empty_cache()

                    # Get reference model logprob
                    ref_logprob = self.forward(
                        self.ref_policy,
                        query_response,
                        response,
                        tokenizer.pad_token_id,
                        context_length,
                        args.temperature,
                    )
                    torch.cuda.empty_cache()
```

#### 3.2.2 处理响应并计算奖励
```1263:1302:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
                    # Response Processing 1. truncate response after the first occurrence of `stop_token_id`
                    postprocessed_response = response
                    if args.stop_token_id is not None:  # handle the edge case when stop_token_id exists but is 0
                        postprocessed_response = truncate_response(
                            args.stop_token_id, tokenizer.pad_token_id, response
                        )
                    # Response Processing 2. run reward model on the truncated responses
                    postprocessed_query_response = torch.cat((query, postprocessed_response), 1)
                    sequence_length = first_true_indices(postprocessed_response == tokenizer.pad_token_id) - 1
                    score = torch.zeros(query.shape[0], device=query.device)
                    if args.reward_model_multiplier:
                        _, score, _ = get_reward(
                            self.reward_model, postprocessed_query_response, tokenizer.pad_token_id, context_length
                        )
                        score *= args.reward_model_multiplier
                    if args.apply_verifiable_reward:
                        # we need to batch the gt to match query.
                        ground_truth = ground_truths[i : i + args.local_rollout_forward_batch_size]
                        dataset = datasets[i : i + args.local_rollout_forward_batch_size]
                        decoded_response = tokenizer.batch_decode(postprocessed_response)
                        # for now, not supporting arb log values in non-fast scripts.
                        verifiable_reward, per_func_reward, _ = apply_verifiable_reward(
                            responses=postprocessed_response,
                            decoded_responses=decoded_response,
                            ground_truths=ground_truth,
                            datasets=dataset,
                            reward_mult=args.verification_reward,
                        )
                        verifiable_reward = torch.tensor(verifiable_reward, device=score.device)
                        verifiable_count = verifiable_reward > 0
                        score += verifiable_reward
                        # For each sample, aggregate each per-function reward into a single dict.
                        for reward_dict in per_func_reward:
                            for key, value in reward_dict.items():
                                per_func_rewards[key].append(value)
                    else:
                        verifiable_count = torch.tensor([0.0], device=device).float()

                    if args.add_r1_style_format_reward:
                        score += format_scores[i : i + args.local_rollout_forward_batch_size]

                    full_value, _, _ = get_reward(
                        self.value_model, query_response, tokenizer.pad_token_id, context_length
                    )
                    value = full_value[:, context_length - 1 : -1].squeeze(-1)
```

#### 3.2.3 计算KL散度和奖励
```1352:1388:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
                # 4. compute rewards
                kl1 = logprobs - ref_logprobs
                kl2 = (kl1) ** 2 / 2
                kl3 = (-kl1).exp() - 1 + kl1
                if args.kl_estimator == "kl1":
                    kl = kl1
                elif args.kl_estimator == "kl2":
                    kl = kl2
                elif args.kl_estimator == "kl3":
                    kl = kl3
                non_score_reward = -args.beta * kl
                non_score_reward_sum = non_score_reward.sum(1)
                rlhf_reward = scores + non_score_reward_sum
                rewards = non_score_reward.clone()
                actual_start = torch.arange(rewards.size(0), device=rewards.device)
                actual_end = torch.where(sequence_lengths_p1 < rewards.size(1), sequence_lengths_p1, sequence_lengths)
                rewards[[actual_start, actual_end]] += scores

                # 5. whiten rewards
                if args.whiten_rewards:
                    rewards = masked_whiten(rewards, mask=~padding_mask_p1, shift_mean=False)
                    rewards = torch.masked_fill(rewards, padding_mask_p1, 0)

                # 6. compute advantages and returns
                lastgaelam = 0
                advantages_reversed = []
                gen_length = responses.shape[1]
                for t in reversed(range(gen_length)):
                    nextvalues = values[:, t + 1] if t < gen_length - 1 else 0.0
                    delta = rewards[:, t] + args.gamma * nextvalues - values[:, t]
                    lastgaelam = delta + args.gamma * args.lam * lastgaelam
                    advantages_reversed.append(lastgaelam)
                advantages = torch.stack(advantages_reversed[::-1], axis=1)
                returns = advantages + values
                advantages = masked_whiten(advantages, ~padding_mask)
                advantages = torch.masked_fill(advantages, padding_mask, 0)
                torch.cuda.empty_cache()
```

### 3.3 策略更新阶段（PPO）

#### 3.3.1 多轮训练
```1390:1464:rl/open-instruct/open_instruct/ppo_vllm_thread_ray_gtrl.py
            # Do multiple epochs of training on on-policy data (PPO-style), with a fresh random shuffle in each epoch
            for epoch_idx in range(args.num_epochs):
                b_inds = np.random.permutation(args.local_total_prompts)
                minibatch_idx = 0
                for mini_batch_start in range(0, args.local_total_prompts, args.local_mini_batch_size):
                    mini_batch_end = mini_batch_start + args.local_mini_batch_size
                    mini_batch_inds = b_inds[mini_batch_start:mini_batch_end]
                    gradient_accumulation_idx = 0
                    # NOTE: deepspeed handles gradient accumulation automatically; see https://github.com/microsoft/DeepSpeed/issues/758#issuecomment-801580724
                    for micro_batch_start in range(0, args.local_mini_batch_size, args.per_device_train_batch_size):
                        # print("micro batch start", micro_batch_start, self.rank)
                        micro_batch_end = micro_batch_start + args.per_device_train_batch_size
                        micro_batch_inds = mini_batch_inds[micro_batch_start:micro_batch_end]
                        mb_advantage = advantages[micro_batch_inds]
                        mb_responses = responses[micro_batch_inds]
                        mb_query_responses = query_responses[micro_batch_inds]
                        mb_logprobs = logprobs[micro_batch_inds]
                        mb_return = returns[micro_batch_inds]
                        mb_values = values[micro_batch_inds]
                        mb_padding_mask_p1 = padding_mask_p1[micro_batch_inds]

                        vpred_temp = get_reward(
                            self.value_model, mb_query_responses, tokenizer.pad_token_id, context_length
                        )
                        vpred_temp = vpred_temp[0]
                        vpred = vpred_temp[:, context_length - 1 : -1].squeeze(-1)
                        vpred = torch.masked_fill(vpred, mb_padding_mask_p1, 0)
                        vpredclipped = torch.clamp(
                            vpred,
                            mb_values - args.cliprange_value,
                            mb_values + args.cliprange_value,
                        )
                        vf_losses1 = torch.square(vpred - mb_return)
                        vf_losses2 = torch.square(vpredclipped - mb_return)
                        vf_loss_max = torch.max(vf_losses1, vf_losses2)
                        vf_loss = 0.5 * masked_mean(vf_loss_max, ~mb_padding_mask_p1)
                        self.value_model.backward(vf_loss * args.vf_coef)
                        self.value_model.step()

                        new_logprobs = self.forward(
                            self.model,
                            mb_query_responses,
                            mb_responses,
                            tokenizer.pad_token_id,
                            context_length,
                            args.temperature,
                        )
                        new_logprobs = torch.masked_fill(new_logprobs, padding_mask[micro_batch_inds], INVALID_LOGPROB)
                        logprobs_diff = new_logprobs - mb_logprobs
                        ratio = torch.exp(logprobs_diff)
                        pg_losses = -mb_advantage * ratio
                        pg_losses2 = -mb_advantage * torch.clamp(ratio, 1.0 - args.cliprange, 1.0 + args.cliprange)
                        pg_loss_max = torch.max(pg_losses, pg_losses2)
                        pg_loss = masked_mean(pg_loss_max, ~padding_mask[micro_batch_inds])
                        loss = pg_loss
                        self.model.backward(loss)
                        self.model.step()
                        with torch.no_grad():
                            vf_clipfrac = masked_mean((vf_losses2 > vf_losses1).float(), ~mb_padding_mask_p1)
                            pg_clipfrac = masked_mean(
                                (pg_losses2 > pg_losses).float(), ~padding_mask[micro_batch_inds]
                            )
                            # print("value model stepped", self.rank, "micro batch start", micro_batch_start)
                            # prob_dist = torch.nn.functional.softmax(logits, dim=-1)
                            # entropy = torch.logsumexp(logits, dim=-1) - torch.sum(prob_dist * logits, dim=-1)
                            approxkl = 0.5 * (logprobs_diff**2).mean()
                            approxkl_stats[epoch_idx, minibatch_idx, gradient_accumulation_idx] = approxkl
                            pg_clipfrac_stats[epoch_idx, minibatch_idx, gradient_accumulation_idx] = pg_clipfrac
                            pg_loss_stats[epoch_idx, minibatch_idx, gradient_accumulation_idx] = pg_loss
                            vf_loss_stats[epoch_idx, minibatch_idx, gradient_accumulation_idx] = vf_loss
                            vf_clipfrac_stats[epoch_idx, minibatch_idx, gradient_accumulation_idx] = vf_clipfrac
                            # entropy_stats[epoch_idx, minibatch_idx, gradient_accumulation_idx] = entropy.mean()
                            ratio_stats[epoch_idx, minibatch_idx, gradient_accumulation_idx] = ratio.mean()
                        gradient_accumulation_idx += 1
                    minibatch_idx += 1
                    # fmt: off
                    del mb_advantage, mb_responses, mb_query_responses, mb_logprobs, mb_return, mb_values, mb_padding_mask_p1
                    del new_logprobs, logprobs_diff, ratio, pg_losses, pg_losses2, pg_loss_max, pg_loss, loss
                    # fmt: on
                    # del everything and empty cache
                    torch.cuda.empty_cache()
                del b_inds, mini_batch_inds
```

## 四、GRPO与PPO的主要区别

### 4.1 GRPO的优势
GRPO（Group Relative Policy Optimization）与PPO的主要区别在于：

1. **不需要价值模型**：GRPO直接使用组内相对奖励，不需要训练价值函数
2. **优势计算方式不同**：
   - PPO：使用GAE（Generalized Advantage Estimation）计算优势
   - GRPO：使用组内标准化奖励作为优势

```1317:1322:rl/open-instruct/open_instruct/grpo_vllm_thread_ray_gtrl.py
                # MAIN GRPO CHANGE: compute group rewards instead of value model output
                mean_grouped_rewards = scores.view(-1, args.number_samples_per_prompt).mean(dim=-1)
                mean_grouped_rewards = mean_grouped_rewards.repeat_interleave(args.number_samples_per_prompt, dim=0)
                std_grouped_rewards = scores.view(-1, args.number_samples_per_prompt).std(dim=-1)
                std_grouped_rewards = std_grouped_rewards.repeat_interleave(args.number_samples_per_prompt, dim=0)
                advantages = (scores - mean_grouped_rewards) / (std_grouped_rewards + 1e-8)
```

3. **损失函数**：GRPO在损失中直接加入KL散度项

```1385:1388:rl/open-instruct/open_instruct/grpo_vllm_thread_ray_gtrl.py
                        # grpo change: directly subtract KL in loss (add)
                        loss = masked_mean(pg_loss_max + (args.beta * kl), ~padding_mask[micro_batch_inds])
                        self.model.backward(loss)
                        self.model.step()
```

## 五、关键组件说明

### 5.1 模型组件
- **策略模型（Policy Model）**：正在训练的主要模型
- **参考模型（Reference Model）**：用于计算KL散度的固定模型
- **价值模型（Value Model）**：仅PPO需要，用于估计状态价值
- **奖励模型（Reward Model）**：可选，用于计算奖励分数

### 5.2 vLLM引擎
- 用于高效生成响应
- 支持多引擎并行生成
- 通过Ray进行分布式管理

### 5.3 奖励函数
- **可验证奖励（Verifiable Reward）**：基于ground truth的奖励
- **奖励模型奖励**：基于训练好的奖励模型
- **格式奖励**：基于响应格式的奖励
- **KL惩罚**：防止策略偏离参考模型太远

### 5.4 DeepSpeed集成
- 使用DeepSpeed ZeRO Stage 3进行参数分片
- 自动处理梯度累积
- 支持大模型训练

## 六、训练流程总结

```
1. 初始化
   ├── 加载tokenizer和数据集
   ├── 创建Ray进程组和vLLM引擎
   ├── 初始化策略模型、参考模型、价值模型（PPO）
   └── 启动训练进程

2. 训练循环（每个training step）
   ├── Rollout阶段
   │   ├── 从数据集采样prompts
   │   ├── 使用vLLM异步生成响应
   │   └── 广播响应到所有进程
   │
   ├── 奖励计算阶段
   │   ├── 计算策略模型和参考模型的logprobs
   │   ├── 处理响应（截断、过滤）
   │   ├── 计算奖励分数（可验证奖励、奖励模型等）
   │   ├── 计算KL散度
   │   ├── 计算优势（PPO: GAE, GRPO: 组内标准化）
   │   └── 计算returns
   │
   └── 策略更新阶段
       ├── 多轮训练（num_epochs）
       ├── 小批量训练（mini batches）
       ├── 梯度累积（micro batches）
       ├── 更新价值模型（仅PPO）
       ├── 更新策略模型（PPO/GRPO）
       └── 记录指标

3. 保存和评估
   ├── 定期保存checkpoint
   ├── 定期评估模型
   └── 记录训练指标到wandb/tensorboard
```

## 七、工具调用机制

### 7.1 可用工具列表

训练时LLM可以调用的工具通过MCP（Model Context Protocol）协议提供。工具注册表定义在：

```21:27:rl/open-instruct/open_instruct/search_utils/mcp_tools.py
MCP_TOOL_REGISTRY = {
    "snippet_search": SemanticScholarSnippetSearchTool,
    "google_search": SerperSearchTool,
    "massive_serve": MassiveServeSearchTool,
    "browse_webpage": Crawl4AIBrowseTool,
    # "browse_webpage": SerperBrowseTool
}
```

#### 7.1.1 搜索工具

1. **snippet_search** (Semantic Scholar Snippet Search)
   - 功能：从学术论文中检索相关文本片段
   - 定义位置：`agent/dr_agent/mcp_backend/main.py` 的 `semantic_scholar_snippet_search` 函数
   - 参数：
     - `query`: 搜索查询字符串
     - `year`: 发表年份过滤（如 "2021-2025"）
     - `limit`: 返回的片段数量
     - `fieldsOfStudy`: 研究领域过滤
   - 用途：查找科学文献中的具体引用和证据

2. **google_search** (Serper Google Search)
   - 功能：通用网页搜索
   - 定义位置：`agent/dr_agent/mcp_backend/main.py` 的 `serper_google_webpage_search` 函数
   - 参数：
     - `query`: 搜索查询
     - `num_results`: 返回结果数量
     - `gl`: 地理位置代码
     - `hl`: 界面语言
   - 用途：查找一般网络信息和资源

3. **massive_serve** (Massive Serve Search)
   - 功能：使用密集段落检索进行大规模文档搜索
   - 定义位置：`agent/dr_agent/mcp_backend/main.py` 的 `massive_serve_search` 函数
   - 参数：
     - `query`: 搜索查询
     - `n_docs`: 返回文档数量
     - `domains`: 搜索域/索引
   - 用途：访问大规模文档集合

#### 7.1.2 浏览工具

4. **browse_webpage** (Crawl4AI Browse)
   - 功能：获取网页内容并提取可读文本
   - 定义位置：`agent/dr_agent/mcp_backend/main.py` 的 `crawl4ai_fetch_webpage_content` 函数
   - 参数：
     - `url`: 要获取的网页URL
     - `ignore_links`: 是否移除markdown中的超链接
     - `use_pruning`: 是否应用内容过滤
     - `bm25_query`: 可选的BM25查询用于内容过滤
   - 用途：打开并阅读网页的完整内容

#### 7.1.3 其他工具（在MCP后端定义但可能未在注册表中）

- **semantic_scholar_search**: 使用Semantic Scholar API搜索学术论文
- **pubmed_search**: 使用PubMed API搜索医学和科学论文
- **serper_google_scholar_search**: 使用Google Scholar搜索学术论文
- **vllm_hosted_reranker**: 使用VLLM托管的reranker对文档进行重排序
- **jina_fetch_webpage_content**: 使用Jina Reader API获取网页内容

### 7.2 工具调用格式

工具通过统一的XML标签格式调用：

```xml
<call_tool name="tool_name">query or parameters</call_tool>
```

示例：
```xml
<call_tool name="google_search">2024 renewable energy market trends</call_tool>
<call_tool name="snippet_search" limit="8" year="2021-2025" fieldsOfStudy="Computer Science, Medicine">large language model retrieval evaluation</call_tool>
<call_tool name="browse_webpage">https://example.com/article</call_tool>
```

### 7.3 工具输出格式

工具执行后，结果会被包装在 `<tool_output>` 标签中：

```xml
<tool_output>
  <snippet id="UNIQUE_ID">content</snippet>
  <snippet id="UNIQUE_ID2">content</snippet>
</tool_output>
```

对于网页浏览：
```xml
<tool_output>
  <webpage id="UNIQUE_ID">content</webpage>
</tool_output>
```

### 7.4 系统提示词

工具的使用说明定义在系统提示词文件中：

- 主要文件：`rl/open-instruct/open_instruct/search_utils/system_prompts/unified_tool_calling_v20250907.yaml`
- 该文件包含：
  - 工具调用格式说明
  - 每个工具的用途和参数
  - 工作流程示例
  - 引用格式要求

### 7.5 工具集成到训练流程

#### 7.5.1 工具注册

在训练脚本中，工具通过以下方式注册：

```1967:1991:rl/open-instruct/open_instruct/grpo_fast.py
    # first, handle the "regular" tools of search and code via actors.
    if args.tools:
        for tool in args.tools:
            class_path = TOOL_CLASS_REGISTRY.get(tool.lower(), None)
            if class_path is None:
                raise ValueError(f"Unknown tool: {tool}")
            # Pass the entire args namespace; ToolActor will filter valid kwargs
            _register_actor_backed_tool(class_path=class_path, init_kwargs=vars(args))

    vllm_engines = create_vllm_engines(
        args.vllm_num_engines,
        args.vllm_tensor_parallel_size,
        args.vllm_enforce_eager,
        tc.tokenizer_name_or_path,
        model_config.model_name_or_path,
        model_config.model_revision,
        args.seed,
        args.vllm_enable_prefix_caching,
        max_len,
        args.vllm_gpu_memory_utilization,
        args.single_gpu_mode,
        pg=pg if args.single_gpu_mode else None,
        tools=tool_objects,
        max_tool_calls=args.max_tool_calls,
    )
```

#### 7.5.2 MCP工具包装器

MCP工具通过 `MCPTool` 类包装：

```57:133:rl/open-instruct/open_instruct/search_utils/mcp_tools.py
class MCPTool(Tool):
    """
    Unlike other tools, this guy handles *all mcp tools*. Why?
    because they share the same end string (</tool>). Hence, we need the parsers
    to work out how to route them. Ideally, this would be more tightly integrated into vllm,
    but for now, this is a bit cleaner.
    """
    def __init__(
        self,
        mcp_tool_names: List[str] | str,
        mcp_parser_name: str = "unified",
        transport_type: str | None = None,
        mcp_host: str | None = None,
        mcp_port: int | None = None,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
        search_api_endpoint: str | None = None,
        start_str: str = "",
        end_str: str | None = None,
        mcp_timeout: int = 180,
        base_url: str | None = None,
        number_documents_to_search: int = 10,
        use_localized_snippets: bool = False,
        context_chars: int = 6000,
        *args,
        **kwargs,
    ):
        self.mcp_tools = []
        self.stop_strings = []
        # Allow selecting transport via arg or env; default to StreamableHttpTransport
        self.transport_type = transport_type or os.environ.get("MCP_TRANSPORT", "StreamableHttpTransport")
        self.mcp_host = mcp_host or os.environ.get("MCP_TRANSPORT_HOST", "0.0.0.0")
        if self.mcp_host is not None:
            os.environ["MCP_TRANSPORT_HOST"] = str(self.mcp_host)
        self.mcp_port = mcp_port or os.environ.get("MCP_TRANSPORT_PORT", 8000)
        if self.mcp_port is not None:
            os.environ["MCP_TRANSPORT_PORT"] = str(self.mcp_port)
        # Transient error retry settings
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        # Support comma-separated string for mcp_tool_names
        if isinstance(mcp_tool_names, str):
            mcp_tool_names = [n.strip() for n in mcp_tool_names.split(",") if n.strip()]
        for mcp_tool_name in mcp_tool_names:
            # filter kwargs so we only pass ones the constructor understands
            mcp_tool_cls = MCP_TOOL_REGISTRY[mcp_tool_name]
            sig = inspect.signature(mcp_tool_cls.__init__)
            valid_params = set(sig.parameters.keys())
            filtered_kwargs = {
                k: v for k, v in kwargs.items() if k in valid_params
            }
            if "base_url" in valid_params:
                filtered_kwargs["base_url"] = base_url
            if "number_documents_to_search" in valid_params:
                filtered_kwargs["number_documents_to_search"] = number_documents_to_search
            if "use_localized_snippets" in valid_params:
                filtered_kwargs["use_localized_snippets"] = use_localized_snippets
            if "context_chars" in valid_params:
                filtered_kwargs["context_chars"] = context_chars
            # special case for crawl4ai
            if mcp_tool_name == "browse_webpage":
                filtered_kwargs["use_docker_version"] = True
                filtered_kwargs["use_ai2_config"] = True
            # basically, we want to defer as much as possible to the mcp tool.
            # this 'tool' actually just passes everything down to the mcp tool.
            self.mcp_tools.append(mcp_tool_cls(
                timeout=mcp_timeout,
                name=mcp_tool_name,
                tool_parser=mcp_parser_name,
                transport_type=self.transport_type,
                **filtered_kwargs,
            ))
            # assign the stop strings from the parser itself.
            self.stop_strings += self.mcp_tools[-1].tool_parser.stop_sequences
        # MCP tool handles its own start and end strings.
        super().__init__(start_str=start_str, end_str=end_str or self.stop_strings[-1])
```

#### 7.5.3 vLLM工具集成

工具通过 `ToolUseLLM` 类集成到vLLM中：

```151:159:rl/open-instruct/open_instruct/tool_utils/tool_vllm.py
class ToolUseLLM(LLM):
    def __init__(self, tools: dict[str, Tool] = None, max_tool_calls: Union[int, dict[str, int]] = 4, *args, **kwargs):
        
        # Convert max_tool_calls to a dict if it's an int
        if isinstance(max_tool_calls, int):
            self.max_tool_calls = {k: max_tool_calls for k in tools.keys()} if tools else {}
        else:
            self.max_tool_calls = max_tool_calls
        # Initialize executor and store for pending tool calls
        self.executor = ThreadPoolExecutor(max_workers=20)
        self.pending_tool_futures = {}
```

### 7.6 训练脚本中的工具配置

在 `train_dr_tulu.sh` 中，工具通过以下参数配置：

```bash
--tools mcp \
--mcp_tool_names 'snippet_search,google_search,browse_webpage' \
--max_tool_calls 10 \
--system_prompt_file open_instruct/search_utils/system_prompts/unified_tool_calling_v20250907.yaml \
--mcp_parser_name v20250824 \
--mcp_server_command "'python -m dr_agent.mcp_backend.main --transport http --port 8003 --host 0.0.0.0 --path /mcp'"
```

### 7.7 MCP服务器

MCP工具通过独立的MCP服务器提供，服务器定义在：
- `agent/dr_agent/mcp_backend/main.py`

服务器使用FastMCP框架，通过HTTP传输协议提供服务。训练时会启动MCP服务器子进程来处理工具调用请求。

### 7.8 工具调用流程

1. **生成阶段**：LLM生成包含工具调用标签的文本
2. **检测工具调用**：vLLM检测到工具调用的结束标签（如 `</tool>`）
3. **路由到工具**：根据工具名称路由到对应的MCP工具
4. **执行工具**：通过MCP协议调用后端服务执行工具
5. **返回结果**：工具结果被包装并返回给LLM
6. **继续生成**：LLM基于工具结果继续生成响应

### 7.9 工具定义位置总结

| 组件 | 位置 |
|------|------|
| 工具注册表 | `rl/open-instruct/open_instruct/search_utils/mcp_tools.py` |
| MCP后端工具实现 | `agent/dr_agent/mcp_backend/main.py` |
| 工具接口基类 | `agent/dr_agent/tool_interface/mcp_tools.py` |
| 系统提示词 | `rl/open-instruct/open_instruct/search_utils/system_prompts/unified_tool_calling_v20250907.yaml` |
| vLLM工具集成 | `rl/open-instruct/open_instruct/tool_utils/tool_vllm.py` |
| 工具Actor | `rl/open-instruct/open_instruct/tool_utils/tool_actor.py` |

## 八、关键参数说明

- `rollout_batch_size`: 每个训练步骤采样的prompt数量
- `number_samples_per_prompt`: 每个prompt生成的响应数量
- `num_epochs`: 对同一批数据训练的轮数
- `num_mini_batches`: 将rollout数据分成的小批量数量
- `beta`: KL散度惩罚系数
- `cliprange`: PPO裁剪范围
- `gamma`: GAE折扣因子
- `lam`: GAE lambda参数
- `max_tool_calls`: 每个工具的最大调用次数
- `mcp_tool_names`: 要启用的MCP工具名称列表
- `mcp_parser_name`: 工具调用解析器版本

