/** 新建空白模板冷启动骨架：按当前所选业务类型生成结构化提示词与输出字段，一键填入即可直接试发。 */
import { appendBlock, outputFormatBlock } from '../shared/aiText'

export interface StarterPromptSpec {
  buttonLabel: string
  defaultTitle: string
  content: string
  outputFields: string
}

interface RawPreset {
  buttonLabel: string
  defaultTitle: string
  body: string
  fields: string[]
}

const PRESETS: Record<string, RawPreset> = {
  policy: {
    buttonLabel: '填入「政策结构化提取」标准骨架',
    defaultTitle: '新建政策打标草稿',
    fields: ['是否政策', '政策类型', '判定简因'],
    body: [
      '# 角色任务',
      '请担任资深政企政策分析专员，阅读下方政策标题与正文，判断其是否属于具有普遍约束力或扶持导向的正式政策文件，并给出分类与简明依据。',
      '',
      '# 待分析材料',
      '政策标题：@【政策标题】',
      '政策正文：@【政策正文】',
      '',
      '# 判定准则',
      '1、重点核查发文主体、文种（通知、意见、办法、方案等）及具体举措，人事任免、会议纪要、单一公示不计入政策。',
      '2、判定简因控制在 80 字以内，直指核心条款，不套话。',
    ].join('\n'),
  },
  customer: {
    buttonLabel: '填入「客户商机研判」标准骨架',
    defaultTitle: '新建客户研判草稿',
    fields: ['主营方向', '信息化需求', '研判依据'],
    body: [
      '# 角色任务',
      '请根据下方企业工商与公开业务信息，提炼该企业的核心主营方向、潜在数字化/信息化建设需求及研判依据。',
      '',
      '# 企业资料',
      '企业名称：@【企业名称】',
      '经营与简介：@【经营范围】',
      '',
      '# 判定准则',
      '1、严格依据给定资料客观提炼，缺失维度填“-”，禁止凭空臆造。',
      '2、研判依据简明扼要，突出与算力、云网、行业数字化的结合点。',
    ].join('\n'),
  },
  bidding: {
    buttonLabel: '填入「招投标项目筛选」标准骨架',
    defaultTitle: '新建招投标筛选草稿',
    fields: ['是否相关', '公告阶段', '筛选理由'],
    body: [
      '# 角色任务',
      '请审阅下方招投标公告内容，判断该项目是否属于政企信息化/数字化相关商机，并识别公告阶段与核心筛选理由。',
      '',
      '# 公告信息',
      '项目名称：@【项目名称】',
      '公告正文：@【公告正文】',
      '',
      '# 判定准则',
      '1、软件开发、云平台、数据治理、智慧城市、算力网络、系统集成等判为「是」，纯土建装修或物资采购判为「否」。',
      '2、筛选理由点明核心采购标的，不超过 60 字。',
    ].join('\n'),
  },
}

export function starterPromptForCategory(category: string): StarterPromptSpec {
  const preset = PRESETS[category] ?? PRESETS.policy!
  return {
    buttonLabel: preset.buttonLabel,
    defaultTitle: preset.defaultTitle,
    content: appendBlock(preset.body, outputFormatBlock(preset.fields)),
    outputFields: preset.fields.join('|'),
  }
}
