import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  TextInput,
  Alert,
  Platform,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { conversationService, ConversationItem } from '../../services/conversation';

interface ConversationListProps {
  currentConversationId?: string;
  onSelectConversation: (conversationId: string) => void;
  onNewChat: () => void;
  visible: boolean;
  onClose: () => void;
  /** Increment this counter to trigger a list refresh (e.g., after sending a message) */
  refreshTrigger?: number;
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'เมื่อสักครู่';
  if (diffMin < 60) return `${diffMin} นาทีที่แล้ว`;
  if (diffHr < 24) return `${diffHr} ชั่วโมงที่แล้ว`;
  if (diffDay < 7) return `${diffDay} วันที่แล้ว`;
  return date.toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });
}

export function ConversationList({
  currentConversationId,
  onSelectConversation,
  onNewChat,
  visible,
  onClose,
  refreshTrigger = 0,
}: ConversationListProps) {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  const fetchConversations = useCallback(async (pageNum = 1, append = false) => {
    setLoading(true);
    try {
      const result = await conversationService.list(pageNum, 20);
      if (append) {
        setConversations((prev) => [...prev, ...result.items]);
      } else {
        setConversations(result.items);
      }
      setTotal(result.total);
      setPage(pageNum);
    } catch (err) {
      console.error('Failed to fetch conversations:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on open AND whenever refreshTrigger increments (e.g., after message sent)
  useEffect(() => {
    if (visible) {
      fetchConversations(1);
    }
  }, [visible, refreshTrigger, fetchConversations]);

  const handleLoadMore = () => {
    if (conversations.length < total && !loading) {
      fetchConversations(page + 1, true);
    }
  };

  const handleRename = async (id: string) => {
    if (!editTitle.trim()) {
      setEditingId(null);
      return;
    }
    try {
      await conversationService.update(id, { title: editTitle.trim() });
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: editTitle.trim() } : c))
      );
    } catch (err) {
      console.error('Failed to rename:', err);
    }
    setEditingId(null);
  };

  const handleDelete = async (id: string) => {
    const doDelete = async () => {
      try {
        await conversationService.delete(id);
        setConversations((prev) => prev.filter((c) => c.id !== id));
        setTotal((t) => t - 1);
        if (id === currentConversationId) {
          onNewChat();
        }
      } catch (err) {
        console.error('Failed to delete:', err);
      }
    };

    if (Platform.OS === 'web') {
      if (window.confirm('ต้องการลบสนทนานี้?')) {
        await doDelete();
      }
    } else {
      Alert.alert('ลบสนทนา', 'ต้องการลบสนทนานี้?', [
        { text: 'ยกเลิก', style: 'cancel' },
        { text: 'ลบ', style: 'destructive', onPress: doDelete },
      ]);
    }
    setMenuOpenId(null);
  };

  const renderItem = ({ item }: { item: ConversationItem }) => {
    const isActive = item.id === currentConversationId;
    const isEditing = editingId === item.id;
    const isMenuOpen = menuOpenId === item.id;

    return (
      <TouchableOpacity
        onPress={() => {
          if (!isEditing) {
            onSelectConversation(item.id);
            setMenuOpenId(null);
          }
        }}
        className={`px-3 py-2.5 mx-2 my-0.5 rounded-lg ${
          isActive
            ? 'bg-blue-100 dark:bg-blue-900/40'
            : 'bg-transparent'
        }`}
        activeOpacity={0.7}
      >
        <View className="flex-row items-start justify-between">
          <View className="flex-1 mr-2">
            {isEditing ? (
              <TextInput
                value={editTitle}
                onChangeText={setEditTitle}
                onSubmitEditing={() => handleRename(item.id)}
                onBlur={() => handleRename(item.id)}
                autoFocus
                className="text-sm text-gray-900 dark:text-white bg-white dark:bg-gray-700 rounded px-2 py-1 border border-blue-400"
                selectTextOnFocus
              />
            ) : (
              <Text
                numberOfLines={1}
                className={`text-sm font-medium ${
                  isActive
                    ? 'text-blue-700 dark:text-blue-300'
                    : 'text-gray-800 dark:text-gray-200'
                }`}
              >
                {item.title || 'สนทนาใหม่'}
              </Text>
            )}
            <Text numberOfLines={1} className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {formatRelativeTime(item.updated_at)}
              {item.message_count > 0 ? ` · ${item.message_count} ข้อความ` : ''}
            </Text>
          </View>

          {/* More menu button */}
          <TouchableOpacity
            onPress={(e) => {
              e.stopPropagation?.();
              setMenuOpenId(isMenuOpen ? null : item.id);
            }}
            className="p-1"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons
              name="ellipsis-horizontal"
              size={16}
              color={isActive ? '#3B82F6' : '#9CA3AF'}
            />
          </TouchableOpacity>
        </View>

        {/* Context menu */}
        {isMenuOpen && (
          <View className="mt-1 bg-white dark:bg-gray-700 rounded-lg shadow-sm border border-gray-200 dark:border-gray-600">
            <TouchableOpacity
              onPress={() => {
                setEditTitle(item.title || '');
                setEditingId(item.id);
                setMenuOpenId(null);
              }}
              className="flex-row items-center px-3 py-2"
            >
              <Ionicons name="pencil-outline" size={14} color="#6B7280" />
              <Text className="text-sm text-gray-700 dark:text-gray-200 ml-2">เปลี่ยนชื่อ</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => handleDelete(item.id)}
              className="flex-row items-center px-3 py-2 border-t border-gray-100 dark:border-gray-600"
            >
              <Ionicons name="trash-outline" size={14} color="#EF4444" />
              <Text className="text-sm text-red-500 ml-2">ลบ</Text>
            </TouchableOpacity>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  if (!visible) return null;

  return (
    <View className="h-full bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700"
      style={{ width: 280 }}
    >
      {/* Header */}
      <View className="px-3 py-3 border-b border-gray-200 dark:border-gray-700">
        <View className="flex-row items-center justify-between">
          <Text className="text-base font-bold text-gray-800 dark:text-white">สนทนา</Text>
          <View className="flex-row items-center gap-1">
            <TouchableOpacity
              onPress={onNewChat}
              className="w-8 h-8 rounded-lg bg-blue-600 items-center justify-center"
            >
              <Ionicons name="add" size={20} color="white" />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={onClose}
              className="w-8 h-8 rounded-lg items-center justify-center"
            >
              <Ionicons name="close" size={20} color="#9CA3AF" />
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* List */}
      {conversations.length === 0 && !loading ? (
        <View className="flex-1 items-center justify-center px-4">
          <Ionicons name="chatbubbles-outline" size={40} color="#9CA3AF" />
          <Text className="text-sm text-gray-400 dark:text-gray-500 mt-2 text-center">
            ยังไม่มีประวัติสนทนา
          </Text>
        </View>
      ) : (
        <FlatList
          data={conversations}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          contentContainerStyle={{ paddingVertical: 4 }}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            loading ? (
              <View className="py-3">
                <ActivityIndicator size="small" color="#3B82F6" />
              </View>
            ) : null
          }
        />
      )}
    </View>
  );
}
