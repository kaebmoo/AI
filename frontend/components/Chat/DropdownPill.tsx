import React, { useRef, useState } from 'react';
import { View, Text, TouchableOpacity, Modal, Pressable, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export interface DropdownItem {
    key: string;
    label: string;
    description?: string;
    icon: string;
    color: string;
}

interface DropdownPillProps {
    /** Heading inside the open list, also read as the pill's accessibility label. */
    title: string;
    items: DropdownItem[];
    selected: string;
    onSelect: (key: string) => void;
    /** Optional row rendered under the list (e.g. a refresh action). */
    footer?: React.ReactNode;
}

const PANEL_WIDTH = 288;

/** Compact selector: a pill showing the current choice that opens an anchored list.
 *  ponytail: Modal + measureInWindow instead of a popover lib — works on web and native. */
export const DropdownPill = ({ title, items, selected, onSelect, footer }: DropdownPillProps) => {
    const [open, setOpen] = useState(false);
    const [anchor, setAnchor] = useState({ x: 16, y: 64 });
    const triggerRef = useRef<any>(null);
    const { width: screenWidth } = useWindowDimensions();

    const current = items.find((i) => i.key === selected) ?? items[0];
    if (!current) return null;

    const openList = () => {
        const show = (x: number, y: number, h: number) => {
            setAnchor({ x: Math.max(8, Math.min(x, screenWidth - PANEL_WIDTH - 8)), y: y + h + 6 });
            setOpen(true);
        };
        if (triggerRef.current?.measureInWindow) {
            triggerRef.current.measureInWindow((x: number, y: number, _w: number, h: number) => show(x, y, h));
        } else {
            setOpen(true);
        }
    };

    return (
        <>
            <TouchableOpacity
                ref={triggerRef}
                onPress={openList}
                accessibilityRole="button"
                accessibilityLabel={`${title}: ${current.label}`}
                className="h-9 flex-row items-center gap-1.5 pl-3 pr-2 rounded-full bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700"
            >
                <Ionicons name={current.icon as any} size={14} color={current.color} />
                <Text numberOfLines={1} className="text-xs font-medium text-gray-900 dark:text-white">{current.label}</Text>
                <Ionicons name="chevron-down" size={14} color="#9CA3AF" />
            </TouchableOpacity>

            <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
                <Pressable className="flex-1" onPress={() => setOpen(false)}>
                    <Pressable
                        onPress={(e) => e.stopPropagation()}
                        className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 py-1"
                        style={{
                            position: 'absolute',
                            left: anchor.x,
                            top: anchor.y,
                            width: PANEL_WIDTH,
                            boxShadow: '0px 8px 24px rgba(0, 0, 0, 0.18)',
                        }}
                    >
                        <Text className="px-4 pt-2 pb-1 text-xs font-semibold text-gray-500 dark:text-gray-400">{title}</Text>
                        <ScrollView style={{ maxHeight: 360 }}>
                            {items.map((item) => {
                                const isSelected = item.key === selected;
                                return (
                                    <TouchableOpacity
                                        key={item.key}
                                        onPress={() => { onSelect(item.key); setOpen(false); }}
                                        accessibilityRole="button"
                                        accessibilityState={{ selected: isSelected }}
                                        className={`flex-row items-center gap-3 px-4 py-2.5 ${isSelected ? 'bg-gray-100 dark:bg-gray-700' : ''}`}
                                    >
                                        <Ionicons name={item.icon as any} size={16} color={item.color} />
                                        <View className="flex-1">
                                            <Text className="text-sm text-gray-900 dark:text-white">{item.label}</Text>
                                            {item.description ? (
                                                <Text numberOfLines={1} className="text-xs text-gray-500 dark:text-gray-400">{item.description}</Text>
                                            ) : null}
                                        </View>
                                        {isSelected ? <Ionicons name="checkmark" size={16} color="#2563EB" /> : null}
                                    </TouchableOpacity>
                                );
                            })}
                        </ScrollView>
                        {footer}
                    </Pressable>
                </Pressable>
            </Modal>
        </>
    );
};
