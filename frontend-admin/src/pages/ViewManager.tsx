import React, { useEffect, useState } from 'react';
import {
    Table, Button, Tag, Space, Card, message, Modal, Typography, Progress, Tooltip, Alert
} from 'antd';
import {
    SyncOutlined, EyeOutlined, ReloadOutlined, SwapOutlined, WarningOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { viewManagerService } from '../services/viewManager';
import type {
    ViewSummaryItem, ViewColumnMappingItem, MissingColumnInfo
} from '../services/viewManager';

const { Text } = Typography;

const MAPPING_TYPE_COLORS: Record<string, string> = {
    alias: 'blue',
    passthrough: 'green',
    expression: 'orange',
};

const ViewManager: React.FC = () => {
    const [views, setViews] = useState<ViewSummaryItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [propagating, setPropagating] = useState<Set<string>>(new Set());

    // Detail modal
    const [detailOpen, setDetailOpen] = useState(false);
    const [detailView, setDetailView] = useState<string>('');
    const [mappings, setMappings] = useState<ViewColumnMappingItem[]>([]);
    const [mappingsLoading, setMappingsLoading] = useState(false);

    // Propagation result modal
    const [resultOpen, setResultOpen] = useState(false);
    const [resultData, setResultData] = useState<{
        view_name: string;
        created: number;
        updated: number;
        skipped: number;
        missing_columns: MissingColumnInfo[];
    } | null>(null);

    useEffect(() => {
        fetchViews();
    }, []);

    const fetchViews = async () => {
        setLoading(true);
        try {
            const data = await viewManagerService.listViews();
            setViews(data.views);
        } catch {
            message.error('Failed to load views');
        } finally {
            setLoading(false);
        }
    };

    const handlePropagate = async (viewName: string) => {
        setPropagating(prev => new Set([...prev, viewName]));
        try {
            const result = await viewManagerService.propagateMetadata(viewName);
            fetchViews();

            if (result.missing_columns.length > 0) {
                // Show detailed result modal
                setResultData(result);
                setResultOpen(true);
            } else {
                message.success(
                    `${viewName}: ${result.created} created, ${result.updated} updated, ${result.skipped} already up-to-date`
                );
            }
        } catch (err: any) {
            message.error(err.response?.data?.detail || 'Propagation failed');
        } finally {
            setPropagating(prev => {
                const next = new Set(prev);
                next.delete(viewName);
                return next;
            });
        }
    };

    const handleViewDetail = async (viewName: string) => {
        setDetailView(viewName);
        setDetailOpen(true);
        setMappingsLoading(true);
        try {
            const data = await viewManagerService.getMappings(viewName);
            setMappings(data.mappings);
        } catch {
            message.error('Failed to load mappings');
        } finally {
            setMappingsLoading(false);
        }
    };

    const viewColumns: ColumnsType<ViewSummaryItem> = [
        {
            title: 'View Name',
            dataIndex: 'view_name',
            key: 'view_name',
            render: (name: string) => <Text strong>{name}</Text>,
        },
        {
            title: 'Source Table',
            dataIndex: 'source_table',
            key: 'source_table',
            render: (name: string) => <Tag>{name}</Tag>,
        },
        {
            title: 'Columns',
            dataIndex: 'mapping_count',
            key: 'mapping_count',
            width: 100,
            align: 'center',
        },
        {
            title: 'Metadata Coverage',
            key: 'coverage',
            width: 200,
            render: (_: any, record: ViewSummaryItem) => {
                const pct = record.mapping_count > 0
                    ? Math.round((record.metadata_with_thai_count / record.mapping_count) * 100)
                    : 0;
                const color = pct >= 80 ? '#52c41a' : pct >= 50 ? '#faad14' : '#ff4d4f';
                return (
                    <Tooltip title={`${record.metadata_with_thai_count}/${record.mapping_count} columns have Thai names`}>
                        <Progress
                            percent={pct}
                            size="small"
                            strokeColor={color}
                            format={() => `${record.metadata_with_thai_count}/${record.mapping_count}`}
                        />
                    </Tooltip>
                );
            },
        },
        {
            title: 'Actions',
            key: 'actions',
            width: 280,
            render: (_: any, record: ViewSummaryItem) => (
                <Space>
                    <Button
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => handleViewDetail(record.view_name)}
                    >
                        Mappings
                    </Button>
                    <Button
                        size="small"
                        type="primary"
                        icon={<SyncOutlined spin={propagating.has(record.view_name)} />}
                        onClick={() => handlePropagate(record.view_name)}
                        loading={propagating.has(record.view_name)}
                    >
                        Propagate Metadata
                    </Button>
                </Space>
            ),
        },
    ];

    const mappingColumns: ColumnsType<ViewColumnMappingItem> = [
        {
            title: 'View Column',
            dataIndex: 'view_column',
            key: 'view_column',
            render: (col: string) => <Text code>{col}</Text>,
        },
        {
            title: '',
            key: 'arrow',
            width: 40,
            align: 'center',
            render: () => <SwapOutlined style={{ color: '#999' }} />,
        },
        {
            title: 'Source Column',
            dataIndex: 'source_column',
            key: 'source_column',
            render: (col: string) => <Text code>{col}</Text>,
        },
        {
            title: 'Source Table',
            dataIndex: 'source_table',
            key: 'source_table',
            render: (name: string) => <Tag>{name}</Tag>,
        },
        {
            title: 'Type',
            dataIndex: 'mapping_type',
            key: 'mapping_type',
            width: 110,
            render: (type: string) => (
                <Tag color={MAPPING_TYPE_COLORS[type] || 'default'}>
                    {type.toUpperCase()}
                </Tag>
            ),
        },
    ];

    const missingColumns: ColumnsType<MissingColumnInfo> = [
        {
            title: 'View Column',
            dataIndex: 'view_column',
            key: 'view_column',
            render: (col: string) => <Text code>{col}</Text>,
        },
        {
            title: 'Source',
            key: 'source',
            render: (_: any, record: MissingColumnInfo) => (
                <Text type="secondary">{record.source_table}.{record.source_column}</Text>
            ),
        },
    ];

    return (
        <div>
            <Card
                title={<><SwapOutlined /> View Manager</>}
                extra={
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={fetchViews}
                        loading={loading}
                    >
                        Refresh
                    </Button>
                }
            >
                <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
                    Manage view-to-source column mappings and propagate metadata (Thai names, summable flags) from raw tables to views.
                </Text>

                <Table
                    columns={viewColumns}
                    dataSource={views}
                    loading={loading}
                    pagination={false}
                    size="middle"
                    rowKey="view_name"
                />
            </Card>

            {/* Column Mappings Modal */}
            <Modal
                title={`Column Mappings: ${detailView}`}
                open={detailOpen}
                onCancel={() => setDetailOpen(false)}
                width={800}
                footer={[
                    <Button key="close" onClick={() => setDetailOpen(false)}>Close</Button>,
                    <Button
                        key="propagate"
                        type="primary"
                        icon={<SyncOutlined />}
                        loading={propagating.has(detailView)}
                        onClick={() => handlePropagate(detailView)}
                    >
                        Propagate Metadata
                    </Button>,
                ]}
            >
                <Table
                    columns={mappingColumns}
                    dataSource={mappings}
                    loading={mappingsLoading}
                    pagination={false}
                    size="small"
                    rowKey="id"
                />
            </Modal>

            {/* Propagation Result Modal */}
            <Modal
                title={<><WarningOutlined style={{ color: '#faad14' }} /> Propagation Result: {resultData?.view_name}</>}
                open={resultOpen}
                onCancel={() => setResultOpen(false)}
                footer={<Button onClick={() => setResultOpen(false)}>OK</Button>}
                width={600}
            >
                {resultData && (
                    <>
                        <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
                            <Text>Created: <Text strong>{resultData.created}</Text></Text>
                            <Text>Updated: <Text strong>{resultData.updated}</Text></Text>
                            <Text>Already up-to-date: <Text strong>{resultData.skipped}</Text></Text>
                        </Space>

                        {resultData.missing_columns.length > 0 && (
                            <>
                                <Alert
                                    type="warning"
                                    showIcon
                                    message={`${resultData.missing_columns.length} columns have no source metadata`}
                                    description="These columns could not be propagated because the source table has no metadata for them. Add metadata to the source table first, then propagate again."
                                    style={{ marginBottom: 12 }}
                                />
                                <Table
                                    columns={missingColumns}
                                    dataSource={resultData.missing_columns.map((m, i) => ({ ...m, key: i }))}
                                    pagination={false}
                                    size="small"
                                />
                            </>
                        )}
                    </>
                )}
            </Modal>
        </div>
    );
};

export default ViewManager;
