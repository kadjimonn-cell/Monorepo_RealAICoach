import React, { useState } from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Text, TouchableOpacity, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { withAlpha } from '../../utils/colorAlpha';

interface PricingFaqSectionProps {
  colors: any;
  isMobile: boolean;
  faq: { q: string; a: string }[];
}

export const PricingFaqSection = ({ colors, faq, isMobile }: PricingFaqSectionProps) => {
  const { tx } = useTranslation();
  const [openIndex, setOpenIndex] = useState<number>(0);

  return (
    <View style={{ gap: 12 }} data-testid="pricing-faq-section" testID="pricing-faq-section">
      <View style={{ gap: 6 }}>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }} data-testid="pricing-faq-label" testID="pricing-faq-label">
          {tx('pricing.faq.label', 'FAQ')}
        </Text>
        <Text style={{ color: colors.text, fontSize: isMobile ? 24 : 28, fontWeight: '900', letterSpacing: -0.7, lineHeight: isMobile ? 30 : 34 }} data-testid="pricing-faq-title" testID="pricing-faq-title">
          {tx('pricing.faq.title', 'Common pricing questions, answered clearly.')}
        </Text>
      </View>

      {faq.map((item, index) => {
        const open = openIndex === index;
        return (
          <View
            key={`${item.q}-${index}`}
            style={{
              borderRadius: isMobile ? 18 : 20,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.card,
              overflow: 'hidden',
            }}
            data-testid={`pricing-faq-${index}`}
            testID={`pricing-faq-${index}`}
          >
            <TouchableOpacity
              onPress={() => setOpenIndex(open ? -1 : index)}
              style={{ paddingHorizontal: isMobile ? 14 : 16, paddingVertical: isMobile ? 14 : 15, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
              data-testid={`pricing-faq-toggle-${index}`}
              testID={`pricing-faq-toggle-${index}`}
            >
              <Text style={{ color: colors.text, fontSize: isMobile ? 13 : 14, fontWeight: '800', flex: 1, lineHeight: isMobile ? 18 : 20 }}>{item.q}</Text>
              <Ionicons name={open ? 'remove' : 'add'} size={18} color={colors.text} />
            </TouchableOpacity>

            {open ? (
              <View style={{ borderTopWidth: 1, borderTopColor: withAlpha(colors.text, '0C'), paddingHorizontal: isMobile ? 14 : 16, paddingVertical: isMobile ? 13 : 14 }} data-testid={`pricing-faq-answer-${index}`} testID={`pricing-faq-answer-${index}`}>
                <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: isMobile ? 19 : 20 }}>{item.a}</Text>
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );
};