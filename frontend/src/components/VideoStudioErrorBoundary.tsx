import React, { Component, ReactNode } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface Props {
  children: ReactNode;
  colors?: {
    bg: string;
    card: string;
    text: string;
    textSec: string;
    error: string;
  };
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

export class VideoStudioErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('VideoStudioErrorBoundary caught error:', error);
    console.error('Error details:', errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      const colors = this.props.colors || {
        bg: 'var(--app-bg)',
        card: 'var(--app-card-bg)',
        text: 'var(--app-text)',
        textSec: 'var(--app-text-sec)',
        error: 'var(--app-error)',
      };

      return (
        <View style={[styles.container, { backgroundColor: colors.bg }]}>
          <View style={[styles.card, { backgroundColor: colors.card }]}>
            <View style={[styles.iconContainer, { backgroundColor: colors.error + '20' }]}>
              <Ionicons name="warning" size={32} color={colors.error} />
            </View>
            
            <Text style={[styles.title, { color: colors.text }]}>
              Something went wrong
            </Text>
            
            <Text style={[styles.message, { color: colors.textSec }]}>
              The Video Creator Studio encountered an error while loading.
            </Text>

            {this.state.error && (
              <View style={[styles.errorBox, { backgroundColor: colors.error + '10', borderColor: colors.error + '30' }]}>
                <Text style={[styles.errorText, { color: colors.error }]} numberOfLines={3}>
                  {this.state.error.message}
                </Text>
              </View>
            )}

            <TouchableOpacity accessibilityLabel="Try Again"
              style={[styles.button, { backgroundColor: colors.error }]}
              onPress={this.handleReset}
            >
              <Ionicons name="refresh" size={18} color="var(--app-primary-text)" />
              <Text style={styles.buttonText}>Try Again</Text>
            </TouchableOpacity>

            {__DEV__ && this.state.errorInfo && (
              <View style={{ marginTop: 16, padding: 12, backgroundColor: 'var(--app-surface-hover)', borderRadius: 8 }}>
                <Text style={{ fontSize: 11, color: 'var(--app-text-muted)', fontFamily: 'monospace' }} numberOfLines={10}>
                  {this.state.errorInfo.componentStack}
                </Text>
              </View>
            )}
          </View>
        </View>
      );
    }

    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    padding: 24,
    borderRadius: 16,
    alignItems: 'center',
    shadowColor: '#000', // @theme-ok shadow constant
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  iconContainer: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
  },
  message: {
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 16,
    lineHeight: 20,
  },
  errorBox: {
    width: '100%',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 16,
  },
  errorText: {
    fontSize: 12,
    fontWeight: '600',
  },
  button: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
    gap: 8,
  },
  buttonText: {
    color: 'var(--app-primary-text)',
    fontSize: 14,
    fontWeight: '600',
  },
});
