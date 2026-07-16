import React, { useEffect, useRef } from 'react';
import { Animated, View } from 'react-native';

export const NovaTypingDots = ({ color }: { color: string }) => {
  const dotsRef = useRef([new Animated.Value(0.25), new Animated.Value(0.25), new Animated.Value(0.25)]);

  useEffect(() => {
    const loops = dotsRef.current.map((value, index) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(index * 160),
          Animated.timing(value, { toValue: 1, duration: 320, useNativeDriver: true }),
          Animated.timing(value, { toValue: 0.25, duration: 320, useNativeDriver: true }),
          Animated.delay((2 - index) * 160),
        ]),
      ),
    );
    loops.forEach((loop) => loop.start());
    return () => loops.forEach((loop) => loop.stop());
  }, []);

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="chat-typing-dots" testID="chat-typing-dots">
      {dotsRef.current.map((value, index) => (
        <Animated.View
          key={index}
          style={{ width: 5, height: 5, borderRadius: 2.5, backgroundColor: color, opacity: value }}
        />
      ))}
    </View>
  );
};
