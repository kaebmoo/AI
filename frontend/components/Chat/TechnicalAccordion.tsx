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
        <View className="mt-2 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <TouchableOpacity
                onPress={() => setExpanded(!expanded)}
                className="flex-row items-center justify-between p-3 bg-gray-50 dark:bg-gray-800"
            >
                <Text className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    Technical Details {executionTime && `(${executionTime.toFixed(0)}ms)`}
                </Text>
                <Ionicons
                    name={expanded ? "chevron-up" : "chevron-down"}
                    size={16}
                    color="#6B7280"
                />
            </TouchableOpacity>

            {expanded && (
                <View className="bg-gray-900 p-3">
                    <Text className="text-xs text-gray-400 mb-1 font-mono">SQL Query:</Text>
                    <SyntaxHighlighter
                        language='sql'
                        style={vs2015}
                        fontSize={12}
                        highlighter={"hljs"}
                    >
                        {sql}
                    </SyntaxHighlighter>
                </View>
            )}
        </View>
    );
};
