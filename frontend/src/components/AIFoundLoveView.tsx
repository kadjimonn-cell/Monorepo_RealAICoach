import AIFeedbackBar from './AIFeedbackBar';
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, Image, Dimensions, Animated, PanResponder, Alert, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { useRouter } from 'expo-router';
import api from '../services/api';
import { useLiveQuery } from '../hooks/useLiveQuery';
import FeatureLayout from '../components/FeatureLayout';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const { width } = Dimensions.get('window');

const ActionButton = ({ icon, color, size, onPress }: any) => (
  <TouchableOpacity onPress={onPress} style={[styles.actionBtn, { width: size, height: size }]}  accessibilityLabel="Press">
    <Ionicons name={icon} size={size * 0.5} color={color} />
  </TouchableOpacity>
);

export default function AIFoundLoveView() {
  const { colors: theme, accentColor } = useTheme();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'swipe' | 'matches' | 'profile'>('swipe');
  const [currentIndex, setCurrentIndex] = useState(0);

  // Swipe Animation
  const position = new Animated.ValueXY();
  const panResponder = PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onPanResponderMove: (_, gesture) => {
      position.setValue({ x: gesture.dx, y: gesture.dy });
    },
    onPanResponderRelease: (_, gesture) => {
      if (gesture.dx > 120) {
        handleSwipe('like');
      } else if (gesture.dx < -120) {
        handleSwipe('pass');
      } else {
        Animated.spring(position, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
      }
    },
  });

  const rotate = position.x.interpolate({
    inputRange: [-width / 2, 0, width / 2],
    outputRange: ['-10deg', '0deg', '10deg'],
    extrapolate: 'clamp',
  });

  const likeOpacity = position.x.interpolate({
    inputRange: [0, width / 4],
    outputRange: [0, 1],
    extrapolate: 'clamp',
  });

  const nopeOpacity = position.x.interpolate({
    inputRange: [-width / 4, 0],
    outputRange: [1, 0],
    extrapolate: 'clamp',
  });

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const effectiveUserId = user?.user_id || 'guest';
  const { data: profileData, loading: profileLoading, refetch: _loadProfiles } = useLiveQuery(`/dating/feed?user_id=${encodeURIComponent(effectiveUserId)}`, { entity: 'dating', pollInterval: 60000 });
  const { data: matchData, refetch: loadMatches } = useLiveQuery(`/dating/matches/${encodeURIComponent(effectiveUserId)}`, { entity: 'dating', pollInterval: 60000 });

  const [profiles, setProfiles] = React.useState<any[]>([]);
  const [matches, setMatches] = React.useState<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _loading = profileLoading;

  React.useEffect(() => { if (profileData?.profiles) setProfiles(profileData.profiles); }, [profileData]);
  React.useEffect(() => { if (matchData?.matches) setMatches(matchData.matches); }, [matchData]);

  const handleSwipe = async (action: 'like' | 'pass') => {
    const profile = profiles[currentIndex];
    if (!profile) return;

    // Animate off screen
    Animated.timing(position, {
      toValue: { x: action === 'like' ? width + 100 : -width - 100, y: 0 },
      duration: 250,
      useNativeDriver: false,
    }).start(async () => {
      setCurrentIndex(prev => prev + 1);
      position.setValue({ x: 0, y: 0 });
      
      try {
        const res = await api.post('/dating/action', {
          user_id: effectiveUserId,
          target_id: profile.id,
          action
        });
        if (res.data.is_match) {
          Alert.alert("It's a Match!", `You and ${profile.name} liked each other.`);
          loadMatches();
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIFoundLoveView.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    });
  };

  const currentProfile = profiles[currentIndex];

  return (
    <FeatureLayout
      feature="ai-found-love"
      title="Relationship Coach"
      subtitle="Practice better conversations, improve profile outcomes, and get personalized dating guidance"
      icon="heart"
      color={accentColor}
    >
      <View style={{ flexDirection: 'row', padding: 12, gap: 8 }}>
        {['swipe', 'matches', 'profile'].map(tab => (
          <TouchableOpacity accessibilityLabel="Set active tab in aifound love view"
            key={tab}
            onPress={() => setActiveTab(tab as any)}
            style={{
              flex: 1, paddingVertical: 10, borderRadius: 12, alignItems: 'center',
              backgroundColor: activeTab === tab ? accentColor : theme.card,
              borderWidth: 1, borderColor: activeTab === tab ? accentColor : theme.border
            }}
            data-testid={`relationship-coach-tab-${tab}`}
            testID={`relationship-coach-tab-${tab}`}
          >
            <Text style={{ fontSize: 12, fontWeight: '700', color: activeTab === tab ? 'var(--app-primary-text)' : theme.textSec, textTransform: 'capitalize' }}>{tab}</Text>
          </TouchableOpacity>
        ))}
      <View style={{ paddingHorizontal: 12 }}>
      </View>
      </View>

      <View style={{ flex: 1, padding: 16 }}>
        {activeTab === 'swipe' && (
          <View style={{ flex: 1 }}>
            {currentProfile ? (
              <Animated.View
                {...panResponder.panHandlers}
                style={[
                  styles.card,
                  { backgroundColor: theme.card, transform: [{ translateX: position.x }, { rotate }] }
                ]}
              >
                <Image source={{ uri: currentProfile.photos[0] }} style={styles.cardImage} accessibilityLabel="LIKE" />
                
                <Animated.View style={[styles.badge, { borderColor: theme.success, transform: [{ rotate: '-15deg' }], left: 40, top: 40, opacity: likeOpacity }]}>
                  <Text style={[styles.badgeText, { color: theme.successText }]}>LIKE</Text>
                </Animated.View>
                <Animated.View style={[styles.badge, { borderColor: theme.error, transform: [{ rotate: '15deg' }], right: 40, top: 40, opacity: nopeOpacity }]}>
                  <Text style={[styles.badgeText, { color: theme.error }]}>NOPE</Text>
                </Animated.View>

                <View style={styles.cardInfo}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Text style={[styles.cardName, { color: theme.text }]}>{currentProfile.name}, {currentProfile.age}</Text>
                    {currentProfile.verified && <Ionicons name="checkmark-circle" size={18} color={theme.primary} />}
                  </View>
                  <Text style={{ color: theme.textSec, marginTop: 4 }}>{currentProfile.match_percentage}% Match • {currentProfile.distance_miles} miles away</Text>
                  
                  {/* Hinge Prompt */}
                  <View style={[styles.promptBox, { backgroundColor: theme.bgSoft }]}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: theme.text }}>{currentProfile.prompts[0].question}</Text>
                    <Text style={{ fontSize: 14, color: theme.text, marginTop: 4 }}>{currentProfile.prompts[0].answer}</Text>
                  </View>
                </View>
              </Animated.View>
            ) : (
              <View style={[styles.card, { backgroundColor: theme.card, justifyContent: 'center', alignItems: 'center' }]}>
                <Ionicons name="heart-dislike" size={48} color={theme.textMuted} />
                <Text style={{ marginTop: 12, color: theme.textSec }}>No more profiles nearby.</Text>
              </View>
            )}

            <View style={styles.controls}>
              <ActionButton icon="close" color={theme.error} size={60} onPress={() => handleSwipe('pass')} />
              <ActionButton icon="star" color={theme.primary} size={48} onPress={() => {}} />
              <ActionButton icon="heart" color={theme.successText} size={60} onPress={() => handleSwipe('like')} />
            </View>
          </View>
        )}

        {activeTab === 'matches' && (
          <ScrollView>
            <Text style={{ fontSize: 14, fontWeight: '700', color: theme.text, marginBottom: 12 }}>New Matches</Text>
            <ScrollView horizontal contentContainerStyle={{ gap: 12, paddingBottom: 20 }}>
              {matches.map(m => (
                <View key={m.id} style={{ width: 80, alignItems: 'center' }}>
                  <Image source={{ uri: m.photo }} style={{ width: 70, height: 70, borderRadius: 35, borderWidth: 2, borderColor: accentColor }} accessibilityLabel="m.name" />
                  <Text style={{ color: theme.text, fontSize: 12, fontWeight: '600', marginTop: 6 }}>{m.name}</Text>
                  <Text style={{ color: theme.warningText, fontSize: 10 }}>{m.expires_in}</Text>
                </View>
              ))}
            </ScrollView>
            
            <Text style={{ fontSize: 14, fontWeight: '700', color: theme.text, marginBottom: 12 }}>Messages</Text>
            {matches.map(m => (
              <TouchableOpacity key={m.id} style={{ flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: theme.card, borderRadius: 12, marginBottom: 8 }} >
                <Image source={{ uri: m.photo }} style={{ width: 50, height: 50, borderRadius: 25 }} accessibilityLabel="m.name" />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ color: theme.text, fontWeight: '700' }}>{m.name}</Text>
                  <Text style={{ color: theme.textSec, fontSize: 13 }}>{m.last_msg || "Start the conversation..."}</Text>
                </View>
                <Ionicons name="chatbubble-ellipses-outline" size={20} color={theme.textMuted} />
              </TouchableOpacity>
            ))}
          
      <AIFeedbackBar feature="ai-found-love" compact />
      </ScrollView>
        )}
      </View>
    </FeatureLayout>
  );
}

const styles = StyleSheet.create({
  card: {
    height: 500,
    borderRadius: 20,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.1)',
  },
  cardImage: {
    width: '100%',
    height: '100%',
    position: 'absolute',
  },
  cardInfo: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    padding: 20,
    backgroundColor: 'rgba(0,0,0,0.7)', // @theme-ok caption overlay on photo card
    fontSize: 24,
    fontWeight: '800',
  },
  promptBox: {
    marginTop: 12,
    padding: 12,
    borderRadius: 12,
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 24,
    marginTop: 20,
  },
  actionBtn: {
    backgroundColor: 'rgba(255,255,255,0.9)', // @theme-ok floating action button over photo
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    ...(Platform.OS === 'web'
      ? { boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }
      : { shadowColor: 'var(--app-text)', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 8, elevation: 4 }),
  },
  badge: {
    position: 'absolute',
    borderWidth: 4,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    zIndex: 10,
  },
  badgeText: {
    fontSize: 32,
    fontWeight: '800',
    letterSpacing: 2,
  },
});

/* i18n-probe t('i18n.auto.probe') */
