import React, { useState } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import SyntaxHighlighter from 'react-native-syntax-highlighter';
import { vs2015 } from 'react-syntax-highlighter/dist/esm/styles/hljs';

interface TechnicalAccordionProps {
    sql: string;
    executionTime?: number;
}

export const TechnicalAccordion = ({ sql, executionTime }: TechnicalAccordionProps) => {
    const [expanded, setExpanded] = useState(false);

    return (
        <View className="mt-2 border border-gray-200/80 dark:border-gray-700/80 rounded-xl overflow-hidden bg-gray-50/50 dark:bg-gray-900/30">
            <TouchableOpacity
                onPress={() => setExpanded(!expanded)}
                className="flex-row items-center justify-between p-3 bg-transparent"
            >
                <View className="flex-row items-center space-x-2">
                    <Ionicons name="code-slash-outline" size={14} color="#6B7280" />
                    <Text className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        Technical Details {executionTime && `(${executionTime.toFixed(0)}ms)`}
                    </Text>
                </View>
                <Ionicons
                    name={expanded ? "chevron-up" : "chevron-down"}
                    size={14}
                    color="#6B7280"
                />
            </TouchableOpacity>

            {expanded && (
                <View className="bg-gray-900 px-3 py-2 border-t border-gray-200/50 dark:border-gray-700/50">
                    <Text className="text-[10px] text-gray-500 mb-1 font-mono uppercase tracking-wider">SQL Query</Text>
                    <SyntaxHighlighter
                        language='sql'
                        style={vs2015}
                        fontSize={12}
                        highlighter={"hljs"}
                        customStyle={{ padding: 0, backgroundColor: 'transparent' }}
                    >
                        {sql}
                    </SyntaxHighlighter>
                </View>
            )}
        </View>
    );
};
