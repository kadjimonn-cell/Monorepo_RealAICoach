import React, { useState, useRef, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  Animated,
  Platform,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LogoSimple } from '../src/components/Logo';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { OnboardingSkeleton, usePageReady } from '../src/components/SkeletonLoaders';

interface OnboardingSlide {
  id: string;
  titleKey: string;
  descKey: string;
  icon: keyof typeof Ionicons.glyphMap;
  showLogo?: boolean;
}

const SLIDES: OnboardingSlide[] = [
  {
    id: '1',
    titleKey: 'onboarding.slide1.title',
    descKey: 'onboarding.slide1.desc',
    icon: 'chatbubbles',
    showLogo: true,
  },
  {
    id: '2',
    titleKey: 'onboarding.slide2.title',
    descKey: 'onboarding.slide2.desc',
    icon: 'grid',
  },
  {
    id: '3',
    titleKey: 'onboarding.slide3.title',
    descKey: 'onboarding.slide3.desc',
    icon: 'globe',
  },
];

export default function OnboardingScreen() {
  const pageReady = usePageReady();
  const router = useRouter();
  const { width, _height } = useWindowDimensions();
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatListRef = useRef<FlatList>(null);
  const scrollX = useRef(new Animated.Value(0)).current;
  const { colors } = useTheme();
  const { t } = useTranslation();

  const C = useMemo(() => ({
    primary: colors.primary,
    primaryLight: colors.primary + '20',
    background: colors.bg,
    text: colors.text,
    textSecondary: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
  }), [colors]);

  const styles = useMemo(() => createStyles(C), [C]);

  const handleSkip = async () => {
    await AsyncStorage.setItem('onboarding_complete', 'true');
    router.replace('/dashboard');
  };

  const handleNext = async () => {
    if (currentIndex < SLIDES.length - 1) {
      flatListRef.current?.scrollToIndex({ index: currentIndex + 1 });
    } else {
      await AsyncStorage.setItem('onboarding_complete', 'true');
      router.replace('/dashboard');
    }
  };

  const onViewableItemsChanged = useRef(({ viewableItems }: any) => {
    if (viewableItems[0]) {
      setCurrentIndex(viewableItems[0].index);
    }
  }).current;

  const renderSlide = ({ item }: { item: OnboardingSlide }) => (
    <View style={[styles.slide, { width }]} data-testid={`onboarding-slide-${item.id}`} testID={`onboarding-slide-${item.id}`}>
      {item.showLogo ? (
        <View style={styles.logoContainer}>
          <LogoSimple size={120} />
        </View>
      ) : (
        <View style={[styles.iconContainer, { backgroundColor: (globalThis as any).__alphaColor(C.primary, '15') }]}>
          <Ionicons name={item.icon} size={80} color={C.primary} />
        </View>
      )}
      <Text style={styles.title} data-testid={`onboarding-title-${item.id}`} testID={`onboarding-title-${item.id}`}>{t(item.titleKey)}</Text>
      <Text style={styles.description} data-testid={`onboarding-description-${item.id}`} testID={`onboarding-description-${item.id}`}>{t(item.descKey)}</Text>
    </View>
  );

  const renderDots = () => (
    <View style={styles.dotsContainer} data-testid="onboarding-dots" testID="onboarding-dots">
      {SLIDES.map((_, index) => {
        const inputRange = [(index - 1) * width, index * width, (index + 1) * width];
        const dotWidth = scrollX.interpolate({
          inputRange,
          outputRange: [8, 24, 8],
          extrapolate: 'clamp',
        });
        const opacity = scrollX.interpolate({
          inputRange,
          outputRange: [0.3, 1, 0.3],
          extrapolate: 'clamp',
        });
        return (
          <Animated.View
            key={index}
            style={[styles.dot, { width: dotWidth, opacity, backgroundColor: C.primary }]}
            data-testid={`onboarding-dot-${index}`} testID={`onboarding-dot-${index}`}
          />
        );
      })}
    </View>
  );

  if (!pageReady) return <OnboardingSkeleton />;
  return (
    <SafeAreaView style={styles.container} data-testid="onboarding-screen" testID="onboarding-screen">
      {/* Skip Button */}
      <TouchableOpacity
        style={styles.skipButton}
        onPress={handleSkip}
        data-testid="onboarding-skip-button" testID="onboarding-skip-button"
        dataSet={{ testid: 'onboarding-skip-button' }}
      >
        <Text style={styles.skipText} data-testid="onboarding-skip-text" testID="onboarding-skip-text">{t('onboarding.skip')}</Text>
      </TouchableOpacity>

      {/* Slides */}
      <FlatList
        ref={flatListRef}
        data={SLIDES}
        renderItem={renderSlide}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={Animated.event(
          [{ nativeEvent: { contentOffset: { x: scrollX } } }],
          { useNativeDriver: false }
        )}
        onViewableItemsChanged={onViewableItemsChanged}
        viewabilityConfig={{ viewAreaCoveragePercentThreshold: 50 }}
        data-testid="onboarding-slides" testID="onboarding-slides"
      />

      {/* Bottom Section */}
      <View style={styles.bottomSection} data-testid="onboarding-bottom-section" testID="onboarding-bottom-section">
        {renderDots()}
        
        <TouchableOpacity
          style={styles.nextButton}
          onPress={handleNext}
          data-testid="onboarding-next-button" testID="onboarding-next-button"
          dataSet={{ testid: 'onboarding-next-button' }}
        >
          <Text style={styles.nextButtonText} data-testid="onboarding-next-label" testID="onboarding-next-label">
            {currentIndex === SLIDES.length - 1 ? t('onboarding.getStarted') : t('onboarding.next')}
          </Text>
          <Ionicons 
            name={currentIndex === SLIDES.length - 1 ? 'checkmark' : 'arrow-forward'} 
            size={20} 
            color={colors.primaryText} 
          />
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const createStyles = (C: any) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: C.background,
  },
  skipButton: {
    position: 'absolute',
    top: Platform.OS === 'ios' ? 60 : 20,
    right: 20,
    zIndex: 1,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  skipText: {
    fontSize: 16,
    fontWeight: '600',
    color: C.textMuted,
  },
  slide: {
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
    paddingTop: 40,
    paddingBottom: 20,
  },
  iconContainer: {
    width: 160,
    height: 160,
    borderRadius: 80,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 48,
  },
  logoContainer: {
    marginBottom: 48,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: C.text,
    textAlign: 'center',
    marginBottom: 16,
  },
  description: {
    fontSize: 16,
    color: C.textSecondary,
    textAlign: 'center',
    lineHeight: 24,
  },
  bottomSection: {
    paddingHorizontal: 24,
    paddingBottom: 40,
  },
  dotsContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 32,
    gap: 8,
  },
  dot: {
    height: 8,
    borderRadius: 4,
  },
  nextButton: {
    backgroundColor: C.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 18,
    borderRadius: 16,
    gap: 8,
  },
  nextButtonText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FEFEFE', // @theme-ok deliberate-high-contrast residual semantic hex (reviewed)
  },
});
