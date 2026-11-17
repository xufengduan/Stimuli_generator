# StimMAS

**Multi-agent AI for psychological stimulus generation.**

[Open StimMAS](https://huggingface.co/spaces/CUHKLPL/stimuli_generator) · [中文上手指南](#中文上手指南) · [Report an issue](https://github.com/xufengduan/Stimuli_generator/issues)

StimMAS helps psychology researchers create experimental materials from a written study design and a few examples. Describe what you need, show the tool what one complete stimulus item looks like, and download the generated items as a CSV file for review.

**New to AI tools? Start with the online app and OpenRouter.** You can follow the complete example below without writing code or installing software. OpenRouter lets you access models from different developers through one account, one API key, and the same API URL. See the [OpenRouter quickstart](https://openrouter.ai/docs/quickstart).

## Contents

- [What the three agents do](#what-the-three-agents-do)
- [Step 1: Set up OpenRouter — recommended](#step-1-openrouter)
- [Step 2: Enter example stimuli](#step-2-examples)
- [Step 3: Describe your stimulus design](#step-3-design)
- [Step 4: Set validation and scoring](#step-4-agents)
- [Step 5: Generate and download](#step-5-output)
- [Use another model or provider](#other-models)
- [Frequently asked questions](#faq)
- [中文上手指南](#中文上手指南)
- [Run locally or develop the app](#local-development)

## What the three agents do

| Agent | What it does | What you provide |
| --- | --- | --- |
| **Generator** | Proposes a new stimulus item. | Example items and your study requirements. |
| **Validator** | Checks mandatory requirements; rejected items are regenerated. | Criteria that should all be true for an acceptable item. |
| **Scorer** | Rates accepted items on dimensions you choose. | Rating descriptions and minimum/maximum scores. |

These are three roles using the model you select. You only need one model configuration and one API key. Their checks and ratings help you screen materials; you should still review and pilot the materials before using them in a study.

<a id="step-1-openrouter"></a>
## Step 1: Set up OpenRouter — recommended

### 1. Create an account and get an API key

1. Open [OpenRouter](https://openrouter.ai/) and sign up or sign in.
2. Open the [API Keys page](https://openrouter.ai/settings/keys), create a key, and copy it. You can give it a recognizable name such as `StimMAS`.
3. For a paid model, add credits to your OpenRouter account through its account/billing settings. Check the model's listed prices before running a large batch. Free models can have stricter limits; see the [OpenRouter FAQ](https://openrouter.ai/docs/faq).
4. Open the [StimMAS online app](https://huggingface.co/spaces/CUHKLPL/stimuli_generator).

An **API key** is a private access code that lets StimMAS send requests using your model account. Paste the key itself, without quotation marks or the word `Bearer`. Keep it out of screenshots and shared documents. If a key is exposed, revoke it on the provider's key page and create a replacement.

### 2. Fill in Parameter Settings

For the first run, use the free OpenRouter preset, [NVIDIA Nemotron 3.5 Super VL (free)](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free). Free endpoints have rate limits; start with a small batch. Find other free options in the [free text model catalog](https://openrouter.ai/models?input_modalities=text&output_modalities=text&variant=free).

| On the StimMAS page | What to select or enter |
| --- | --- |
| **Model** | Keep **Predefined Models** selected. |
| **Model Configuration → Model name** | Select **nvidia/nemotron-3.5-super-vl:free (OpenRouter)** from the dropdown. |
| **API URL** | Filled automatically: `https://openrouter.ai/api/v1/chat/completions` |
| **Advanced Parameters** | Leave the two default rows: `max_tokens` / `Number` / `2000`; `temperature` / `Number` / `0.7`. |
| **API Key** | Paste the key you just created **on OpenRouter**. The eye button shows or hides it. |

The page initially selects **DeepSeek**. Change the dropdown to the **OpenRouter** option before pasting an OpenRouter key. Use your OpenRouter key for this NVIDIA model; no separate NVIDIA key is needed.

**What do these unfamiliar terms mean?**

| Term | Plain-language meaning | Example for this walkthrough |
| --- | --- | --- |
| **Provider** | The service receiving the requests and charging your account. | OpenRouter |
| **Model name** | The exact identifier of the AI model to use. | `nvidia/nemotron-3.5-super-vl:free` |
| **API URL** | The web address where StimMAS sends requests. It is different from the provider's homepage. | `https://openrouter.ai/api/v1/chat/completions` |
| **API Key** | Your private access code, obtained from that provider. | Your own OpenRouter key; the text in this guide is not a working key. |

StimMAS uses OpenRouter's [chat completions endpoint](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion). If you need to enter the URL manually, copy the **entire** address above, including `/chat/completions`.

### 3. Leave Advanced Parameters at their defaults for now

You fill in ordinary form rows; StimMAS builds the JSON automatically. There is no need to write JSON for the default settings.

| Parameter | Type | Value | Meaning |
| --- | --- | --- | --- |
| `max_tokens` | Number | `2000` | Limits the length of a model response. This is **not** the number of stimulus items. |
| `temperature` | Number | `0.7` | Controls sampling variability. A lower value generally gives less variable responses; it does not guarantee correctness. |

![Advanced Parameters form with automatic JSON preview](docs/images/stimmas-advanced-parameters.jpg)

To add a setting later, click **Add parameter**. For example, if your chosen model supports it, enter `top_p` / `Number` / `0.9`. Parameter support varies by model, so leave unfamiliar settings alone during your first run.

<details>
<summary>Optional: parameter types and JSON preview</summary>

| Type | How to enter a value | Example syntax |
| --- | --- | --- |
| Number | Enter a number without quotes. | `2000` or `0.7` |
| Text | Enter text without surrounding quotes. | `hello` |
| Boolean | Select true or false. | `false` |
| JSON | Enter a valid structured JSON value. | `["a", "b"]` or `{"enabled": true}` |

The last two columns illustrate value syntax; they are not additional parameters to send to every model. Only add parameter names and values supported by your provider and model. Duplicate names, invalid numbers, and invalid JSON must be corrected before generation can start.

Click **JSON preview** to inspect the generated settings. With the two default rows it shows:

```json
{
  "max_tokens": 2000,
  "temperature": 0.7
}
```

The preview is read-only. Edit the form rows to change it. Remove a row with its trash button; removing every row sends an empty settings object and leaves optional parameters to the provider's defaults.

</details>

<a id="step-2-examples"></a>
## Step 2: Enter example stimuli

This walkthrough creates English sentences in **active** and **passive** voice. One item contains a verb, a name, and both sentence versions. The goal is to generate **new items following the examples**, rather than run an experiment on participants.

In **Stimulus Design → Example stimuli**:

1. The first item starts with one blank row. Click **Add component** three times to make four rows.
2. Fill **Item 1** using the table below. Put the label in **Components** and its corresponding text in **Content**.
3. Click **Add item**, then fill the new **Item 2** with the same component labels. Repeat for **Item 3**.

| Components — use these labels in every item | Content for Item 1 | Content for Item 2 | Content for Item 3 |
| --- | --- | --- | --- |
| `Verb` | eat | read | paint |
| `Name` | Alice | Ben | Clara |
| `Active Condition` | Alice eats an apple. | Ben reads the letter. | Clara paints a wall. |
| `Passive Condition` | An apple is eaten by Alice. | The letter is read by Ben. | A wall is painted by Clara. |

**Avoid repeats:** Put elements that must be unique across stimulus items (e.g., verbs or names) in separate components, and list these components before those that use them.

Here, `Verb` and `Name` come before `Active Condition` and `Passive Condition`. The same verb and name should appear in both sentences **within** an item; different items should use different verbs and names. Keep the component labels and their order consistent across all examples. Use distinct labels within each item.

**Add component / Delete component** adds or removes the last component row across all example items. **Add item** creates another complete example with the same number of rows. Fill every cell; delete unwanted rows or items instead of leaving them blank.

<a id="step-3-design"></a>
## Step 3: Describe your stimulus design

The **Stimulus design** box starts with an editable template. Replace the bracketed prompts with your study requirements, or replace the entire box with this complete example:

```text
We are designing stimuli for an experiment investigating how active and passive voice affect sentence comprehension in adult English speakers.

Each stimulus item should contain four components in this order: Verb, Name, Active Condition, and Passive Condition.

The experiment includes two conditions:

- Active Condition: A simple English sentence in the present tense, with the named person as the agent.
- Passive Condition: A passive-voice version of the same sentence, using a by-phrase that names the same agent.

All stimuli should meet the following requirements:

- Use the same verb, name, and object in both sentences within an item.
- Give every new item a verb and a name that have not appeared in the examples or earlier generated items.
- Use common transitive verbs, familiar objects, and plausible everyday events.
- Use a singular subject and grammatically correct present-tense verb forms.
- Avoid idioms, ambiguous pronouns, and emotionally disturbing content.
- Keep the component labels exactly as Verb, Name, Active Condition, and Passive Condition.

Stimuli across conditions should be matched for meaning, vocabulary, and event plausibility. Allow the grammatical changes required to form the passive voice; the passive sentence need not have the same word count as the active sentence.
```

For your own study, specify the language, participant group, conditions, required content, exclusions, and properties to control. Only require matching that is compatible with your manipulation. For instance, active and passive sentences naturally differ in grammatical form and often in length.

<a id="step-4-agents"></a>
## Step 4: Set validation and scoring

### Validator: requirements that every item must pass

Under **Agent Property Settings → Validator**, fill the first row and click **Add Validator's property** for additional rows. These examples can be copied directly:

| Properties | Description |
| --- | --- |
| `SameMeaning` | The active and passive sentences describe the same event with the same agent and object. |
| `CorrectVoice` | Active Condition is in active voice. Passive Condition is in passive voice and contains a by-phrase naming the agent. |
| `SameVerbAndName` | Both sentences use the verb specified in Verb, with the appropriate inflection, and the name specified in Name. |
| `Grammatical` | Both sentences are grammatical English sentences in the present tense. |

Write each criterion so that **true means acceptable**. For example, use “The sentences contain no idioms,” rather than “The sentences contain idioms.” All criteria must pass for an item to be accepted.

### Scorer: dimensions for comparing accepted items

Under **Scorer**, fill all four columns. Click **Add Scorer's aspect** to add the second row:

| Aspects | Description | Min score | Max score |
| --- | --- | --- | --- |
| `Fluency` | Rate how natural and easy to read both sentences are. 0 = very unnatural; 10 = fully natural. Use the lower rating if the two sentences differ. | `0` | `10` |
| `Plausibility` | Rate how plausible the described event is in everyday life. 0 = highly implausible; 10 = highly plausible. | `0` | `10` |

Scores must have non-negative integer bounds, and the maximum must exceed the minimum. Explain the direction and endpoints in the description. A score does not have to use a 0–10 scale, and a low score does not automatically reject an item: use the Validator for mandatory requirements.

**Want help drafting these tables?** After entering your examples, design, and model settings, click **Auto-generate properties**. This calls the selected model and fills the Validator and Scorer tables. Review and edit the suggestions before generating stimuli; this step also uses your API account.

For a first run, leave **Individual Criteria Validation** and **Individual Aspect Scoring** unchecked. When enabled, these options use a separate model call for each criterion or aspect, increasing the number of calls and potentially the running time and cost.

<a id="step-5-output"></a>
## Step 5: Generate and download

1. Under **Output → The number of items**, enter `5` for a small first run.
2. Click **Generate stimulus** and keep the page open while it runs.
3. Follow the progress and the **Generator**, **Validator**, and **Scorer** panels in **Agent Logs**. Rejected proposals may be regenerated before an item is accepted.
4. When the run finishes, the app initiates a **CSV download**. Check your browser's downloads folder and open the file in Excel, R, SPSS, or another analysis tool.

In this example, **5 items means 5 active/passive pairs: 10 sentences in total**, plus each item's Verb and Name components. The supplied examples show the desired format and are not the five new items you requested.

Each item can involve several model calls for generation, validation, scoring, and retries. Start with a small batch and check your provider's usage before generating a full stimulus set.

| Control | How to use it |
| --- | --- |
| **Stop** | Requests a stop. An in-flight model request may need to finish; completed items are saved for a partial download if available. |
| **Clear all** | Resets the form, examples, agent settings, API key, and logs. Restores the design template, default advanced parameters, and **DeepSeek** preset. Reselect OpenRouter if you use it. |
| **Agent Logs filters** | Focus on outputs, warnings/retries, or errors. Use the item selector to inspect a particular item. |
| **Raw logs** | Shows the underlying log text when you need more detail. |

### What is in the CSV?

Each row is one generated item. Component labels and values are expanded into paired columns. For the four-component example, you would expect `Key1` / `Content1` through `Key4` / `Content4`:

| Example column | Meaning | Illustrative value |
| --- | --- | --- |
| `stimulus_id` | Generated item number. | `1` |
| `Key1` / `Content1` | First component label and value. | `Verb` / `wash` |
| `Key2` / `Content2` | Second component label and value. | `Name` / `David` |
| `Key3` / `Content3` | Third component label and value. | `Active Condition` / `David washes a cup.` |
| `Key4` / `Content4` | Fourth component label and value. | `Passive Condition` / `A cup is washed by David.` |
| `Fluency`, `Plausibility` | Model ratings for the aspects you defined. | Numeric values within your configured ranges. |
| `validation_fails`, `repetition_count` | Diagnostic counts from attempts to obtain the item. | Non-negative integers. |
| `scoring_error`, when present | A rating could not be obtained or did not meet the expected format. | Inspect the affected item and missing ratings. |

Missing ratings are not automatically replaced with zero. Review missing values as well as the texts. Download and keep the CSV; the running app is not permanent storage. For reproducibility, also save your design, examples, criteria, rating scales, model ID, parameter settings, and date. Do not include your API key in that record.

<a id="other-models"></a>
## Use another model or provider

### Find a different model on OpenRouter

**We recommend OpenRouter for trying and comparing models:** you can keep the same API URL and OpenRouter key while changing the model ID. Browse the [free model catalog with text input and output filters](https://openrouter.ai/models?input_modalities=text&output_modalities=text&variant=free).

1. Open a model's page and copy its exact identifier. For example, the [Nemotron 3.5 Super VL (free) page](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free) uses `nvidia/nemotron-3.5-super-vl:free`. Copy the identifier, rather than the display title “NVIDIA: Nemotron 3.5 Super VL (free)”.
2. In StimMAS, click **Custom Model**. **This clears the preset model name and API URL.** Fill in both fields again.
3. Enter your chosen identifier in **Model name**. Keep the full provider prefix, such as `nvidia/`.
4. Paste `https://openrouter.ai/api/v1/chat/completions` in **API URL** and use your **OpenRouter** key in **API Key**.
5. Check the model's price, availability, and supported parameters, then run a small pilot. StimMAS uses `json_object` for OpenRouter and other non-OpenAI endpoints, with field requirements in the prompt and application-side checks. Direct OpenAI requests retain `json_schema`. Models must support the selected output format. StimMAS needs text responses in the requested JSON format; models can differ in how reliably they follow that format.

For example, a fully filled custom configuration for the model used in the tutorial is:

```text
Model:       Custom Model
Model name:  nvidia/nemotron-3.5-super-vl:free
API URL:     https://openrouter.ai/api/v1/chat/completions
API Key:     paste your own OpenRouter key here
```

### Common model names and URLs

OpenRouter is the recommended starting point; direct DeepSeek and OpenAI access are alternatives if you already use those services. The URLs below are complete chat completions endpoints.

| Provider | Example Model name | Complete API URL | Where to get the matching key |
| --- | --- | --- | --- |
| **OpenRouter — recommended** | `nvidia/nemotron-3.5-super-vl:free` | `https://openrouter.ai/api/v1/chat/completions` | [OpenRouter API keys](https://openrouter.ai/settings/keys) |
| DeepSeek | `deepseek-flash` | `https://api.deepseek.com/chat/completions` | [DeepSeek API keys](https://platform.deepseek.com/api_keys) |
| OpenAI | `gpt-5.4` | `https://api.openai.com/v1/chat/completions` | [OpenAI API keys](https://platform.openai.com/api-keys) |

For the listed OpenRouter and OpenAI presets, choose the corresponding option under **Predefined Models** and paste that provider's key. The app's DeepSeek preset currently displays `deepseek-chat`; the [current DeepSeek quickstart](https://api-docs.deepseek.com/) uses `deepseek-flash`. To use the DeepSeek example above, select **Custom Model** and copy its model name and full URL from the table.

For other services, use **Custom Model** with a public HTTP(S), OpenAI-compatible chat completions endpoint; local/private endpoints and redirects are not supported. Model IDs and availability depend on the provider.

<a id="faq"></a>
## Frequently asked questions

| Question or problem | What to do |
| --- | --- |
| **Do I need to know Python, React, or JSON?** | No. Use the online app and the default parameter form. Local installation is optional. |
| **Can I use my ChatGPT login or subscription as the API key?** | Paste a key created on the selected API provider's key page. A chat account password or subscription is not an API key. |
| **The model name or API URL is blank.** | Switching to Custom Model clears both. Refill both fields, or switch to Predefined Models and select the OpenRouter preset. |
| **401 / invalid API key** | Check for extra spaces and confirm the key belongs to the selected provider. Use an OpenRouter key with the OpenRouter URL. |
| **402 / insufficient credits** | Check your provider's balance and any key spending limit. |
| **404 / model not found** | Check the full model ID and API URL. On OpenRouter, include the prefix, e.g., `nvidia/nemotron-3.5-super-vl:free`. |
| **429 / rate limit** | Check the provider's rate limits and retry later. Free models may have tighter limits. |
| **Unsupported parameter / 400** | Check which parameter the provider rejects. Remove that row from Advanced Parameters and try a small run again. |
| **Invalid JSON or incomplete model response** | Try increasing `max_tokens`, simplifying the design, or choosing a model that follows structured-output instructions more reliably. |
| **Repeated validation failures** | Inspect Validator logs. Check for contradictory design requirements or criteria that an acceptable item would fail. |
| **The app seems slow.** | Multiple checks and retries can take time. Inspect the logs and provider status. Stop and wait for any partial results before retrying. |
| **No CSV appeared.** | Check browser download permissions and downloads. If no items finished before stopping, there may be no partial file. |
| **The online app is starting or reconnecting.** | Wait for the Space to start. If a connection fails, check your network; save any downloaded results before refreshing. |
| **Can AI ratings replace human norming?** | Treat them as screening information. Independently verify relevant properties, review the materials, and pilot or norm them as your study requires. |

## 中文上手指南

**第一次使用，推荐直接打开 [StimMAS 网页](https://huggingface.co/spaces/CUHKLPL/stimuli_generator)，并使用 OpenRouter。无需安装软件，也不需要会编程。**

你只需要准备几条示例材料和实验要求。StimMAS 会让三个 AI 角色依次生成材料、检查硬性要求、评价材料质量，最后下载 CSV 表格。这三个角色共用你选择的模型，不需要分别注册三个账号。

### 1. 注册 OpenRouter，拿到自己的 Key

1. 打开 [OpenRouter](https://openrouter.ai/)，注册或登录。
2. 进入 [API Keys 页面](https://openrouter.ai/settings/keys)，创建一个 Key。名称可以填 `StimMAS`，然后复制生成的 Key。
3. 如果使用付费模型，在 OpenRouter 的账户/账单设置中充值。先查看所选模型的价格，再从少量材料开始试用。免费模型也可能有调用次数限制；可以查看 [OpenRouter FAQ](https://openrouter.ai/docs/faq)。
4. 打开 [StimMAS 网页](https://huggingface.co/spaces/CUHKLPL/stimuli_generator)。

**API Key 就是让工具使用你账户的私人通行码。** 在下表对应位置粘贴你自己的 Key，不要加引号，也不要加 `Bearer`。不要把 Key 放进截图、论文附件或共享文件；如果泄露，在 OpenRouter 上撤销后重新创建。

### 2. 对照填写 Parameter Settings

网页刚打开时默认选择的是 DeepSeek，**请先改成 OpenRouter**。OpenRouter 预设使用免费模型 `nvidia/nemotron-3.5-super-vl:free`。其他免费模型可以在[免费文本模型列表](https://openrouter.ai/models?input_modalities=text&output_modalities=text&variant=free)中找到；免费接口也有调用频率和额度限制，建议先少量试跑：

| 网页上的字段 | 应该怎么填 |
| --- | --- |
| **Model** | 保持 **Predefined Models**，也就是使用工具已经准备好的模型配置。 |
| **Model Configuration → Model name** | 在下拉菜单中选择 **nvidia/nemotron-3.5-super-vl:free (OpenRouter)**。 |
| **API URL** | 工具自动填好：`https://openrouter.ai/api/v1/chat/completions`，无需修改。 |
| **Advanced Parameters** | 先保持默认两行：`max_tokens` / `Number` / `2000`；`temperature` / `Number` / `0.7`。 |
| **API Key** | 粘贴刚才在 **OpenRouter** 创建的 Key。眼睛按钮可以显示或隐藏它。 |

几个容易混淆的词，可以这样理解：

| 名称 | 含义与完整例子 |
| --- | --- |
| **Provider：服务平台** | 你注册、充值、获取 Key 的地方。本教程使用 **OpenRouter**。 |
| **Model name：模型编号** | 告诉平台要调用哪个 AI。本例是 `nvidia/nemotron-3.5-super-vl:free`，包括斜杠前的 `nvidia/`。 |
| **API URL：请求地址** | StimMAS 将你的要求发往哪里。本例完整地址是 `https://openrouter.ai/api/v1/chat/completions`，不能只填 `https://openrouter.ai`。选择预设模型时会自动填写。 |
| **API Key：账户通行码** | 必须从对应平台获取。本例调用 NVIDIA 开发的模型，也用 **OpenRouter 的 Key**，不需要另一个 NVIDIA Key。 |

**强烈推荐新手使用 OpenRouter**：以后想尝试不同开发者的模型，通常只需要修改模型编号，仍然使用相同的 OpenRouter 地址和 Key。浏览你想用的模型：[免费文本模型列表](https://openrouter.ai/models?input_modalities=text&output_modalities=text&variant=free)。

Advanced Parameters 也不需要自己写 JSON：`max_tokens = 2000` 是一次回复的长度上限，**不是生成 2000 条材料**；`temperature = 0.7` 控制回答的变化程度，并不代表准确率。默认值可以先不动。点击 **JSON preview** 只是查看工具自动生成的参数。

以后需要添加参数时，点击 **Add parameter**，依次填写参数名、类型和值。例如，模型支持 `top_p` 时可以填 `top_p` / `Number` / `0.9`。不同模型支持的参数可能不同，不确定就先保留默认值。类型说明和表单截图见上方 [Advanced Parameters 说明](#step-1-openrouter)。

### 3. 填几条完整的示例材料

下面用“主动句与被动句的理解”实验作为练习。**一个 Item 是一整组材料，包含一个动词、一个人名，以及两个条件的句子。**

在 **Stimulus Design → Example stimuli** 中，先点击三次 **Add component**，把 Item 1 从一行增加到四行，然后填写下表的 Item 1。再点击 **Add item** 创建 Item 2、Item 3，并填写对应内容。

| Components（每个 Item 都用相同的标签） | Item 1 的 Content | Item 2 的 Content | Item 3 的 Content |
| --- | --- | --- | --- |
| `Verb` | eat | read | paint |
| `Name` | Alice | Ben | Clara |
| `Active Condition` | Alice eats an apple. | Ben reads the letter. | Clara paints a wall. |
| `Passive Condition` | An apple is eaten by Alice. | The letter is read by Ben. | A wall is painted by Clara. |

左侧 **Components** 是每一部分的名称，例如 `Verb`；右侧 **Content** 才是实际内容，例如 `eat`。每个 Item 都有自己的一张表，标签和顺序保持一致，同一张表内的标签不要重名。

**避免跨材料重复：** 如果不同 Item 之间的动词、人名不能重复，就像上表这样把它们分别列成独立组件，放在使用它们的句子之前。同一 Item 的主被动句需要共享动词和人名；不同 Item 才需要使用不同的动词和人名。

**Add component / Delete component** 会同时为所有示例增加/删除最后一行；**Add item** 增加一整条示例。新增的格子需要全部填好，不要留空。

### 4. 填写 Stimulus design

这个框是写给 AI 的材料要求。网页里的方括号内容是待替换的提示，请不要原样保留。第一次可以直接复制以下完整内容，生成英文主被动句材料：

```text
我们正在为一项研究英语主动句与被动句理解的实验设计材料，参与者为成年英语使用者。

每个 Item 按以下顺序包含四个组件：Verb、Name、Active Condition、Passive Condition。组件标签必须保持这四个英文名称。

实验包含两个条件：
- Active Condition：使用一般现在时的简单英语主动句，人名指代动作的执行者。
- Passive Condition：与主动句含义相同的被动句，用 by 短语注明同一个动作执行者。

所有材料必须符合以下要求：
- 同一 Item 的两个句子使用相同的动词、人名和宾语，并使用正确的词形变化。
- 每个新 Item 的动词和人名都不能与示例或此前生成的 Item 重复。
- 使用常见及物动词、常见物体和合理的日常事件。
- 使用单数主语和语法正确的一般现在时。
- 避免习语、指代不清的代词，以及令人不适的情绪性内容。

两个条件应在含义、词汇和事件合理性上匹配。允许被动语态所需的语法变化，不要求两个句子的词数完全相同。
```

改成自己的实验时，交代清楚研究问题、材料语言、参与者、条件、必须包含/必须避免的内容，以及需要控制的属性。不要同时提出互相冲突的要求。

### 5. 配置 Validator 和 Scorer

**Validator 是硬性检查：每条要求都满足才接受这个 Item。** 在 **Agent Property Settings → Validator** 中，第一列 **Properties** 填一个简短名称，第二列 **Description** 填具体判断标准。用 **Add Validator's property** 增加行：

| Properties | Description |
| --- | --- |
| `SameMeaning` | 主动句与被动句描述相同事件，动作执行者和宾语相同。 |
| `CorrectVoice` | Active Condition 是主动句；Passive Condition 是被动句，并含有注明同一执行者的 by 短语。 |
| `SameVerbAndName` | 两个句子都使用 Verb 中指定的动词及其正确词形，并使用 Name 中指定的人名。 |
| `Grammatical` | 两个句子都是语法正确的一般现在时英语句子。 |

每条标准都写成“满足时应当返回 true”的形式。例如写“句子不含习语”，不要写“句子含有习语”。

**Scorer 是质量评分，便于你之后排序和筛选。** 填写 **Aspects**、**Description**、**Min score**、**Max score** 四列，用 **Add Scorer's aspect** 增加行：

| Aspects | Description | Min score | Max score |
| --- | --- | --- | --- |
| `Fluency` | 评价两个句子的自然流畅程度。0 = 非常不自然；10 = 完全自然。如果两句表现不同，取较低的一句作为本项评分。 | `0` | `10` |
| `Plausibility` | 评价句子描述的事件在日常生活中的合理程度。0 = 极不合理；10 = 非常合理。 | `0` | `10` |

分数上下限填非负整数，最大值要大于最小值。低分不会自动淘汰材料；必须满足的要求应当放在 Validator 中。AI 评分也需要研究者检查。

也可以在填好模型、示例和实验要求后，点击 **Auto-generate properties** 让 AI 起草这两个表格，然后自己检查、修改。这一步同样会调用模型、使用 API 额度。

第一次使用时，保持 **Individual Criteria Validation** 和 **Individual Aspect Scoring** 不勾选。勾选后会为每条标准/每个评分维度单独调用模型，调用次数和耗时、费用都可能增加。

### 6. 先生成 5 个 Item，再下载检查

1. 在 **Output → The number of items** 填 `5`。这表示生成 5 组新材料，也就是本例的 5 对主被动句，共 10 个句子。
2. 点击 **Generate stimulus**，保持页面打开。下方 **Agent Logs** 可以看到生成、检查、评分和重试的过程。
3. 完成后网页会发起 CSV 下载，在浏览器的下载文件夹中找到结果，用 Excel、R 或 SPSS 打开。
4. 逐条检查内容与评分，再决定是否扩大生成数量。生成一条材料可能需要多次模型调用，先看小批量结果和平台用量，再运行整套材料。

CSV 中每行是一组 Item。`Key1` 是第一个组件的标签（例如 `Verb`），`Content1` 是对应内容（例如 `wash`）；后面的 `Key2 / Content2` 等以此类推。`Fluency` 等列是你设置的评分维度。评分缺失不会被当作 0 分；出现 `scoring_error` 时，需要检查受影响的材料。更多列的含义见上方 [CSV 说明](#step-5-output)。

**Stop** 会请求停止，可能需要等待正在执行的请求结束；如果已有完成的 Item，会保存并下载部分结果。**Clear all** 会重置整个表单并清除 Key，模型也会恢复到 DeepSeek；再次使用 OpenRouter 时要重新选择。

下载并保存 CSV，同时保留实验要求、示例、检查与评分标准、模型编号、参数和运行日期，便于以后复现。不要把 Key 一起保存到共享记录中。正式使用材料前，仍需按研究需要进行人工审核、预实验或常模评定。

### 7. 换一个 OpenRouter 模型怎么填？

在这个 [免费文本模型列表](https://openrouter.ai/models?input_modalities=text&output_modalities=text&variant=free) 中打开模型页面，复制完整模型编号。例如 [Nemotron 3.5 Super VL (free)](https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free) 的编号是 `nvidia/nemotron-3.5-super-vl:free`，不是页面显示标题 `NVIDIA: Nemotron 3.5 Super VL (free)`。

回到 StimMAS 点击 **Custom Model**。这会清空模型名称和 URL，需要把下面两项都填上：

```text
Model name：nvidia/nemotron-3.5-super-vl:free（换模型时，替换为那个模型的完整编号）
API URL：https://openrouter.ai/api/v1/chat/completions
API Key：粘贴你自己的 OpenRouter Key
```

地址和 Key 保持不变，只替换模型编号即可。先查看模型价格、可用性和参数支持情况，并少量试跑；不同模型遵守 JSON 输出要求的能力可能不同。其他平台的完整配置见上方 [Common model names and URLs](#other-models)。

### 常见问题速查

| 遇到的情况 | 先检查什么 |
| --- | --- |
| 不知道 API URL 填什么 | 选 **Predefined Models → nvidia/nemotron-3.5-super-vl:free (OpenRouter)**，URL 会自动填好。 |
| 提示 Key 错误 / 401 | Key 是否来自 OpenRouter？模型是否也选了 OpenRouter？粘贴时有没有多余空格、引号？ |
| 提示余额不足 / 402 | 检查平台余额以及 Key 的消费上限。 |
| 提示模型找不到 / 404 | 模型编号是否完整？OpenRouter 的编号通常包含 `开发者/模型`，还要检查完整 URL。 |
| 提示调用太频繁 / 429 | 查看平台的频率限制，稍后重试；免费模型可能限制更严。 |
| 提示参数不支持 | 删除 Advanced Parameters 中被报错指出的参数，再少量试跑。 |
| 总是检查不通过 | 看 Validator 日志，检查实验要求是否矛盾，或标准是否写反。 |
| 没有下载文件 | 检查浏览器下载权限和下载列表；如果停止前没有任何完成的 Item，可能没有部分结果。 |

<a id="local-development"></a>
## Run locally or develop the app

**This section is optional.** Online users do not need Python, Node.js, Git, or any of the commands below. Running locally still requires a supported model service and the matching API key.

### Local installation

Python 3.11 is recommended for the current setup. Install Python and Git first, then open a terminal:

```bash
git clone https://github.com/xufengduan/Stimuli_generator.git
cd Stimuli_generator
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
stimulus-generator webui --host 127.0.0.1
```

The example above is for macOS/Linux. On Windows PowerShell, replace the environment creation and activation commands with:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

Then run the same `python -m pip install -e .` and `stimulus-generator webui --host 127.0.0.1` commands. Keep the terminal open and visit [http://127.0.0.1:5001](http://127.0.0.1:5001) in your browser. Press `Ctrl+C` in the terminal to stop the server.

The command name remains `stimulus-generator` although the interface is called **StimMAS**. You can also launch it with `python run.py webui --host 127.0.0.1`. To use another port, append `--port 5002` and open `http://127.0.0.1:5002`.

### Frontend development and checks

Flask serves the committed `static/ui-react.js` bundle. Node.js is needed only when developing the frontend. After editing React sources, rebuild and commit the bundle:

```bash
npm ci
npm run build
npm test
```

The React components provide the typed Advanced Parameters form, interface transitions, and animated title waves. Animations respect reduced-motion preferences and pause when the title is out of view or the page is hidden.

For backend regression checks:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

These tests use simulated model responses and do not consume API credits.

| File or directory | Purpose |
| --- | --- |
| `webpage.html` | Main page and field help. |
| `static/script.js`, `static/styles.css` | Form workflow, logs, and styling. |
| `frontend/` | React components, parameter serialization, and bundle build. |
| `static/ui-react.js` | Prebuilt browser bundle. |
| `stimulus_generator/app.py` | Web server, sessions, API proxy, and CSV downloads. |
| `stimulus_generator/backend.py` | Generation, validation, scoring, and retries. |
| `stimulus_generator/cli.py`, `run.py` | Local launch commands. |
| `tests/` | Backend and frontend regression tests. |

## Feedback and related tools

Report problems or suggest improvements through [GitHub Issues](https://github.com/xufengduan/Stimuli_generator/issues). Include the steps you followed and the error text; remove API keys before sharing screenshots or logs.

For conducting behavioral experiments **on language models**, see [MacBehaviour](https://github.com/xufengduan/MacBehaviour), a related R package. StimMAS focuses on preparing stimulus materials.

## License

Released under the [Apache License 2.0](LICENSE).
