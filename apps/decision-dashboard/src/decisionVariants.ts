import type { DecisionVariantOption } from './data/types';

export const ACTIVE_DECISION_VARIANT_ID = 'active_v3';
export const DEFAULT_DECISION_VARIANT_ID = 'shadow_v3.3.3';

export const DECISION_VARIANT_KIND = {
  ACTIVE: 'active',
  SHADOW: 'shadow',
  OTHER: 'other',
} as const;

export type DecisionVariantKind = typeof DECISION_VARIANT_KIND[keyof typeof DECISION_VARIANT_KIND];

type VariantLike = Pick<DecisionVariantOption, 'variantId' | 'kind' | 'source' | 'isDefault' | 'displayLabel' | 'label'> | undefined;

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
  return variant.displayLabel || variant.label || variant.variantId;
}
