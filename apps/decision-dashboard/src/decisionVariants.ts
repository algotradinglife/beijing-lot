import type { DecisionVariantOption } from './data/types';

export const ACTIVE_DECISION_VARIANT_ID = 'active_v3';
export const DEFAULT_DECISION_VARIANT_ID = '';

export const DECISION_VARIANT_KIND = {
  ACTIVE: 'active',
  SHADOW: 'shadow',
  OTHER: 'other',
} as const;

export type DecisionVariantKind = typeof DECISION_VARIANT_KIND[keyof typeof DECISION_VARIANT_KIND];

type VariantLike = Pick<
  DecisionVariantOption,
  'variantId' | 'kind' | 'source' | 'isDefault' | 'displayLabel' | 'label' | 'version' | 'versionId' | 'available' | 'defaultable' | 'readinessStatus' | 'degradedReason'
> | undefined;

export function decisionVariantKind(variant: VariantLike): DecisionVariantKind {
  if (!variant) return DECISION_VARIANT_KIND.OTHER;
  if (variant.kind === DECISION_VARIANT_KIND.ACTIVE || variant.kind === DECISION_VARIANT_KIND.SHADOW) return variant.kind;
  if (variant.source === 'structured_shadow_csv' || variant.variantId.startsWith('shadow_')) {
    return DECISION_VARIANT_KIND.SHADOW;
  }
  if (variant.isDefault || variant.source === 'active_snapshot' || variant.variantId === ACTIVE_DECISION_VARIANT_ID) {
    return DECISION_VARIANT_KIND.ACTIVE;
  }
  return DECISION_VARIANT_KIND.OTHER;
}

export function isActiveDecisionVariant(variant: VariantLike) {
  return decisionVariantKind(variant) === DECISION_VARIANT_KIND.ACTIVE;
}

export function isShadowDecisionVariant(variant: VariantLike) {
  return decisionVariantKind(variant) === DECISION_VARIANT_KIND.SHADOW;
}

export function decisionVersionLabel(variant: VariantLike) {
  if (!variant) return '';
  const id = variant.variantId || '';
  const base = shortVersion(variant.versionId, variant.version, id, variant.displayLabel, variant.label);
  const role = decisionVersionRole(variant);
  return [base, role].filter(Boolean).join(' ');
}

export function decisionVersionDescription(variant: VariantLike) {
  if (!variant) return '';
  const id = variant.variantId.toLowerCase();
  const version = shortVersion(variant.versionId, variant.version, variant.variantId, variant.displayLabel, variant.label);
  if (variant.available === false || variant.readinessStatus === 'degraded') {
    if (id.includes('execution_strict')) return '执行产物未就绪，仅作诊断；生成后才可投注参考。';
    return variant.degradedReason ? '当前版本未就绪，仅作诊断。' : '当前版本未就绪。';
  }
  if (id.includes('execution_late_proxy')) {
    if (version === 'v4.2.0005') return 'v4.2.0005 备选观察版：继承 v4.2 coverage/ROI，新增极值 SP/source q guard；不作为默认。';
    return `${version || 'v4.2.0004'} 备选观察版：coverage/ROI 有潜力，但需防范异常 SP/q 带偏；不作为默认。`;
  }
  if (id.includes('execution_strict')) return `${version || 'v4.2.0004'} 严格等待观察版，用于审计晚盘刷新前的停牌逻辑；不作为默认。`;
  if (id.includes('shadow_v3.3.3')) return '默认稳定决策链：先解决胜率，q 主要用于保护和增厚。';
  if (id === ACTIVE_DECISION_VARIANT_ID) return '旧版快照，用于对照。';
  if (decisionVariantKind(variant) === DECISION_VARIANT_KIND.SHADOW) return '影子决策链版本。';
  return variant.source ? '当前可选决策版本。' : '';
}

function decisionVersionRole(variant: NonNullable<VariantLike>) {
  const id = variant.variantId.toLowerCase();
  if (id.includes('execution_late_proxy')) return '备选观察';
  if (id.includes('execution_strict')) return '严格观察';
  if (id.includes('shadow_v3.3.3')) return '默认稳定';
  if (id === ACTIVE_DECISION_VARIANT_ID) return '旧版';
  if (decisionVariantKind(variant) === DECISION_VARIANT_KIND.SHADOW) return '影子版';
  return variant.label && !looksInternal(variant.label) ? variant.label : '';
}

function shortVersion(...values: Array<string | undefined>) {
  for (const value of values) {
    const text = String(value || '').trim();
    if (!text) continue;
    const semantic = text.match(/(?:^|[_\-\s])v?(\d+)\.(\d+)\.(\d{1,4})/i) ?? text.match(/^v?(\d+)\.(\d+)\.(\d{1,4})/i);
    if (semantic) {
      const [, major, minor, patch] = semantic;
      const patchText = patch.length >= 4 ? patch : String(Number(patch));
      return `v${Number(major)}.${Number(minor)}.${patchText}`;
    }
    const active = text.match(/^active_v(\d+)$/i);
    if (active) return `v${Number(active[1])}.0`;
    const simple = text.match(/^v(\d+)$/i);
    if (simple) return `v${Number(simple[1])}.0`;
  }
  const fallback = values.find((value) => value && !looksInternal(value));
  return fallback || '';
}

function looksInternal(value?: string) {
  const text = String(value || '');
  return text.includes('_') || text.length > 28;
}
