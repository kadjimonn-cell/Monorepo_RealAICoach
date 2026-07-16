import React from 'react';
import { View } from 'react-native';
import Markdown, { MarkdownStyles } from 'react-native-markdown-display';
import { useTheme } from '../context/ThemeContext';

interface Props {
  content: string;
}

export default function MarkdownDisplayInner({ content }: Props) {
  const { colors: theme } = useTheme();

  const styles: MarkdownStyles = {
    body: {
      color: theme.text,
      fontSize: 15,
      lineHeight: 24,
    },
    heading1: {
      color: theme.text,
      fontSize: 22,
      fontWeight: '700',
      marginVertical: 10,
    },
    heading2: {
      color: theme.text,
      fontSize: 18,
      fontWeight: '700',
      marginVertical: 8,
    },
    heading3: {
      color: theme.text,
      fontSize: 16,
      fontWeight: '700',
      marginVertical: 6,
    },
    bullet_list: {
      marginVertical: 8,
    },
    ordered_list: {
      marginVertical: 8,
    },
    bullet_list_icon: {
      color: theme.primary,
      fontSize: 18,
    },
    ordered_list_icon: {
      color: theme.primary,
      fontSize: 15,
      fontWeight: 'bold',
    },
    code_block: {
      backgroundColor: theme.bgSoft,
      padding: 10,
      borderRadius: 8,
      marginVertical: 8,
      fontFamily: 'monospace',
      borderWidth: 1,
      borderColor: theme.border,
    },
    code_inline: {
      backgroundColor: theme.bgSoft,
      color: theme.primary,
      fontWeight: 'bold',
      fontFamily: 'monospace',
    },
    blockquote: {
      backgroundColor: theme.bgSoft,
      borderLeftWidth: 4,
      borderLeftColor: theme.primary,
      paddingHorizontal: 12,
      paddingVertical: 8,
      marginVertical: 8,
    },
    table: {
      borderWidth: 1,
      borderColor: theme.border,
      borderRadius: 8,
      marginVertical: 8,
    },
    tr: {
      borderBottomWidth: 1,
      borderBottomColor: theme.border,
      flexDirection: 'row',
    },
    th: {
      padding: 8,
      fontWeight: '700',
      backgroundColor: theme.bgSoft,
      flex: 1,
    },
    td: {
      padding: 8,
      flex: 1,
    },
    link: {
      color: theme.primary,
      textDecorationLine: 'underline',
    },
    strong: {
      fontWeight: '700',
      color: theme.text,
    },
    em: {
      fontStyle: 'italic',
      color: theme.text,
    },
  };

  return (
    <View>
      <Markdown style={styles}>
        {content}
      </Markdown>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
