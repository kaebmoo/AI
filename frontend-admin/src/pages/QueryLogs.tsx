import React, { useState, useEffect } from 'react';
import {
    Card, Table, Tag, DatePicker, Select, Space, Button,
    Modal, Typography, Descriptions, message
} from 'antd';
import { ReloadOutlined, SearchOutlined, EyeOutlined } from '@ant-design/icons';
import api from '../services/api';
import dayjs from 'dayjs';

const { Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;

interface QueryLog {
    id: number;
    user_id: number;
    user_email: string;
    question: string;
    generated_sql: string | null;
    sql_result_summary: string | null;
    ai_response: string | null;
    tokens_used: number;
    execution_time_ms: number;
    context_name: string | null;
    feedback_rating: number | null;
    created_at: string | null;
}

const QueryLogs: React.FC = () => {
    const [loading, setLoading] = useState(true);
    const [logs, setLogs] = useState<QueryLog[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(20);
    const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);
    const [contextFilter, setContextFilter] = useState<string | undefined>(undefined);
    const [detailModal, setDetailModal] = useState<QueryLog | null>(null);

    const fetchLogs = async (p = page, ps = pageSize) => {
        try {
            setLoading(true);
            const params: Record<string, any> = {
                skip: (p - 1) * ps,
                limit: ps,
            };
            if (dateRange && dateRange[0]) params.date_from = dateRange[0].toISOString();
            if (dateRange && dateRange[1]) params.date_to = dateRange[1].toISOString();
            if (contextFilter) params.context = contextFilter;

            const response = await api.get('/admin/query-logs', { params });
            setLogs(response.data.items);
            setTotal(response.data.total);
        } catch (err: any) {
            message.error('Failed to load query logs');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchLogs(1); }, []);

    const handleSearch = () => {
        setPage(1);
        fetchLogs(1);
    };

    const columns = [
        {
            title: 'Time',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 150,
            render: (date: string | null) => date ? dayjs(date).format('DD/MM HH:mm:ss') : '-',
        },
        {
            title: 'User',
            dataIndex: 'user_email',
            key: 'user_email',
            width: 140,
            ellipsis: true,
            render: (email: string) => <Text ellipsis style={{ maxWidth: 120 }}>{email}</Text>,
        },
        {
            title: 'Context',
            dataIndex: 'context_name',
            key: 'context_name',
            width: 90,
            render: (ctx: string | null) => ctx ? <Tag color="blue">{ctx}</Tag> : <Tag>auto</Tag>,
        },
        {
            title: 'Question',
            dataIndex: 'question',
            key: 'question',
            ellipsis: true,
        },
        {
            title: 'Time (ms)',
            dataIndex: 'execution_time_ms',
            key: 'execution_time_ms',
            width: 100,
            sorter: (a: QueryLog, b: QueryLog) => (a.execution_time_ms || 0) - (b.execution_time_ms || 0),
            render: (ms: number) => {
                const sec = ms / 1000;
                const color = sec > 30 ? 'red' : sec > 15 ? 'orange' : 'green';
                return <Tag color={color}>{sec.toFixed(1)}s</Tag>;
            },
        },
        {
            title: 'Tokens',
            dataIndex: 'tokens_used',
            key: 'tokens_used',
            width: 80,
            render: (t: number) => t ? t.toLocaleString() : '-',
        },
        {
            title: '',
            key: 'actions',
            width: 60,
            render: (_: any, record: QueryLog) => (
                <Button
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => setDetailModal(record)}
                />
            ),
        },
    ];

    return (
        <div style={{ padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2 style={{ margin: 0 }}>Query Logs</h2>
                <Space>
                    <RangePicker
                        showTime
                        onChange={(dates) => setDateRange(dates as any)}
                        allowClear
                    />
                    <Select
                        placeholder="Context"
                        allowClear
                        style={{ width: 120 }}
                        onChange={setContextFilter}
                        options={[
                            { value: 'revenue', label: 'Revenue' },
                            { value: 'expense', label: 'Expense' },
                            { value: 'transfer_price', label: 'Transfer Price' },
                        ]}
                    />
                    <Button icon={<SearchOutlined />} type="primary" onClick={handleSearch}>Search</Button>
                    <Button icon={<ReloadOutlined />} onClick={() => fetchLogs()}>Refresh</Button>
                </Space>
            </div>

            <Card>
                <Table
                    dataSource={logs}
                    columns={columns}
                    rowKey="id"
                    size="small"
                    loading={loading}
                    pagination={{
                        current: page,
                        pageSize,
                        total,
                        showSizeChanger: true,
                        showTotal: (t) => `Total ${t} queries`,
                        onChange: (p, ps) => {
                            setPage(p);
                            setPageSize(ps);
                            fetchLogs(p, ps);
                        },
                    }}
                />
            </Card>

            {/* Detail Modal */}
            <Modal
                title="Query Detail"
                open={!!detailModal}
                onCancel={() => setDetailModal(null)}
                footer={null}
                width={800}
            >
                {detailModal && (
                    <Descriptions column={1} bordered size="small">
                        <Descriptions.Item label="ID">{detailModal.id}</Descriptions.Item>
                        <Descriptions.Item label="User">{detailModal.user_email}</Descriptions.Item>
                        <Descriptions.Item label="Time">
                            {detailModal.created_at ? dayjs(detailModal.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="Context">
                            {detailModal.context_name || 'auto'}
                        </Descriptions.Item>
                        <Descriptions.Item label="Execution Time">
                            {(detailModal.execution_time_ms / 1000).toFixed(2)}s
                        </Descriptions.Item>
                        <Descriptions.Item label="Tokens">{detailModal.tokens_used}</Descriptions.Item>
                        <Descriptions.Item label="Question">
                            <Paragraph>{detailModal.question}</Paragraph>
                        </Descriptions.Item>
                        <Descriptions.Item label="Generated SQL">
                            <Paragraph
                                copyable
                                style={{
                                    background: '#f5f5f5',
                                    padding: 8,
                                    borderRadius: 4,
                                    fontFamily: 'monospace',
                                    fontSize: 12,
                                    whiteSpace: 'pre-wrap',
                                }}
                            >
                                {detailModal.generated_sql || 'N/A'}
                            </Paragraph>
                        </Descriptions.Item>
                        <Descriptions.Item label="Data Summary">
                            <Paragraph
                                ellipsis={{ rows: 5, expandable: true }}
                                style={{ fontSize: 12 }}
                            >
                                {detailModal.sql_result_summary || 'N/A'}
                            </Paragraph>
                        </Descriptions.Item>
                        <Descriptions.Item label="AI Response">
                            <Paragraph
                                ellipsis={{ rows: 5, expandable: true }}
                            >
                                {detailModal.ai_response || 'N/A'}
                            </Paragraph>
                        </Descriptions.Item>
                    </Descriptions>
                )}
            </Modal>
        </div>
    );
};

export default QueryLogs;
