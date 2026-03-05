import React, { useEffect, useState } from 'react';
import {
    Table, Button, Select, Tag, Space, Card, message, Modal, Typography, Input, Popconfirm
} from 'antd';
import {
    SyncOutlined, RobotOutlined, SaveOutlined, ThunderboltOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
    getFamilies, analyzeFamilies, batchUpdateFamilies, autoPopulateFamilies,
} from '../services/dimensionFamilies';
import type {
    DimensionFamilyItem, DimensionFamilyColumn, DimensionFamilySuggestion
} from '../services/dimensionFamilies';
import { contextService } from '../services/contextService';

const { Text, Paragraph } = Typography;

// Flat row for the editable table
interface FamilyRow {
    key: string;
    column_name: string;
    family_name: string;
    source: string;
}

const SOURCE_COLORS: Record<string, string> = {
    db: 'green',
    auto: 'blue',
    ai: 'purple',
    mixed: 'orange',
};

const DimensionFamilies: React.FC = () => {
    const [tables, setTables] = useState<string[]>([]);
    const [selectedTable, setSelectedTable] = useState<string>('');
    const [families, setFamilies] = useState<DimensionFamilyItem[]>([]);
    const [rows, setRows] = useState<FamilyRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [analyzing, setAnalyzing] = useState(false);
    const [dirty, setDirty] = useState(false);
    const [analyzeModalOpen, setAnalyzeModalOpen] = useState(false);
    const [suggestions, setSuggestions] = useState<DimensionFamilySuggestion[]>([]);
    const [llmReasoning, setLlmReasoning] = useState('');
    const [providerUsed, setProviderUsed] = useState('');

    // Fetch available views from active contexts
    useEffect(() => {
        (async () => {
            try {
                const data = await contextService.getAll();
                const views = data.contexts
                    .filter((c: any) => c.is_active && c.main_view)
                    .map((c: any) => c.main_view);
                const uniqueViews = [...new Set(views)] as string[];
                setTables(uniqueViews);
                if (uniqueViews.length > 0 && !selectedTable) {
                    setSelectedTable(uniqueViews[0]);
                }
            } catch {
                message.error('Failed to load views from contexts');
            }
        })();
    }, []);

    // Fetch families when table changes
    useEffect(() => {
        if (selectedTable) fetchFamilies();
    }, [selectedTable]);

    const fetchFamilies = async () => {
        setLoading(true);
        try {
            const data = await getFamilies(selectedTable);
            setFamilies(data.families);
            setRows(flattenFamilies(data.families));
            setDirty(false);
        } catch {
            message.error('Failed to load dimension families');
        } finally {
            setLoading(false);
        }
    };

    const flattenFamilies = (fams: DimensionFamilyItem[]): FamilyRow[] => {
        const result: FamilyRow[] = [];
        for (const fam of fams) {
            for (const col of fam.columns) {
                result.push({
                    key: col.column_name,
                    column_name: col.column_name,
                    family_name: fam.family_name,
                    source: col.source,
                });
            }
        }
        return result.sort((a, b) => a.family_name.localeCompare(b.family_name) || a.column_name.localeCompare(b.column_name));
    };

    // Get all unique family names for the dropdown
    const allFamilyNames = [...new Set(rows.map(r => r.family_name))].sort();

    const handleFamilyChange = (columnName: string, newFamily: string) => {
        setRows(prev =>
            prev.map(r => r.column_name === columnName ? { ...r, family_name: newFamily, source: 'db' } : r)
        );
        setDirty(true);
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const assignments = rows.map(r => ({
                column_name: r.column_name,
                dimension_group: r.family_name || null,
            }));
            const result = await batchUpdateFamilies(selectedTable, assignments);
            message.success(`Saved ${result.updated_count} assignments`);
            setFamilies(result.families);
            setRows(flattenFamilies(result.families));
            setDirty(false);
        } catch {
            message.error('Failed to save');
        } finally {
            setSaving(false);
        }
    };

    const handleAutoPopulate = async () => {
        setLoading(true);
        try {
            const result = await autoPopulateFamilies(selectedTable, false);
            message.success(`Auto-detected and saved ${result.updated_count} assignments`);
            setFamilies(result.families);
            setRows(flattenFamilies(result.families));
            setDirty(false);
        } catch {
            message.error('Auto-populate failed');
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyze = async () => {
        setAnalyzing(true);
        try {
            const data = await analyzeFamilies(selectedTable);
            setSuggestions(data.suggested_families);
            setLlmReasoning(data.llm_reasoning);
            setProviderUsed(data.provider_used);
            setAnalyzeModalOpen(true);
        } catch {
            message.error('AI analysis failed');
        } finally {
            setAnalyzing(false);
        }
    };

    const handleApplySuggestions = () => {
        // Convert AI suggestions into rows
        const newRows: FamilyRow[] = [];
        for (const sug of suggestions) {
            for (const col of sug.columns) {
                newRows.push({
                    key: col,
                    column_name: col,
                    family_name: sug.family_name,
                    source: 'ai',
                });
            }
        }
        // Merge: AI suggestions override existing, keep columns not in suggestions
        const suggestedCols = new Set(newRows.map(r => r.column_name));
        const merged = [
            ...rows.filter(r => !suggestedCols.has(r.column_name)),
            ...newRows,
        ].sort((a, b) => a.family_name.localeCompare(b.family_name) || a.column_name.localeCompare(b.column_name));
        setRows(merged);
        setDirty(true);
        setAnalyzeModalOpen(false);
        message.info('AI suggestions applied. Click Save to persist.');
    };

    const columns: ColumnsType<FamilyRow> = [
        {
            title: 'Column Name',
            dataIndex: 'column_name',
            key: 'column_name',
            sorter: (a, b) => a.column_name.localeCompare(b.column_name),
        },
        {
            title: 'Family',
            dataIndex: 'family_name',
            key: 'family_name',
            render: (value: string, record: FamilyRow) => (
                <Select
                    value={value}
                    style={{ width: 200 }}
                    onChange={(v) => handleFamilyChange(record.column_name, v)}
                    options={[
                        ...allFamilyNames.map(f => ({ label: f, value: f })),
                    ]}
                    showSearch
                    allowClear={false}
                    dropdownRender={menu => (
                        <>
                            {menu}
                            <div style={{ padding: '4px 8px', borderTop: '1px solid #f0f0f0' }}>
                                <Input
                                    size="small"
                                    placeholder="New family name..."
                                    onPressEnter={(e) => {
                                        const val = (e.target as HTMLInputElement).value.trim();
                                        if (val) handleFamilyChange(record.column_name, val);
                                    }}
                                />
                            </div>
                        </>
                    )}
                />
            ),
            filters: allFamilyNames.map(f => ({ text: f, value: f })),
            onFilter: (value, record) => record.family_name === value,
        },
        {
            title: 'Source',
            dataIndex: 'source',
            key: 'source',
            width: 100,
            render: (source: string) => (
                <Tag color={SOURCE_COLORS[source] || 'default'}>{source.toUpperCase()}</Tag>
            ),
        },
    ];

    // Summary table for families overview
    const familySummary = allFamilyNames.map(name => {
        const cols = rows.filter(r => r.family_name === name);
        return {
            key: name,
            family_name: name,
            column_count: cols.length,
            columns_list: cols.map(c => c.column_name).join(', '),
            source: cols.every(c => c.source === 'db') ? 'db' :
                    cols.every(c => c.source === 'auto') ? 'auto' : 'mixed',
        };
    });

    return (
        <div>
            <Card
                title="Dimension Families"
                extra={
                    <Space>
                        <Select
                            value={selectedTable}
                            onChange={setSelectedTable}
                            style={{ width: 200 }}
                            options={tables.map(t => ({ label: t, value: t }))}
                            placeholder="Select view"
                        />
                        <Button
                            icon={<ThunderboltOutlined />}
                            onClick={handleAutoPopulate}
                            loading={loading}
                        >
                            Auto-Detect
                        </Button>
                        <Button
                            icon={<RobotOutlined />}
                            onClick={handleAnalyze}
                            loading={analyzing}
                        >
                            AI Analyze
                        </Button>
                        <Button
                            icon={<SyncOutlined />}
                            onClick={fetchFamilies}
                            loading={loading}
                        >
                            Refresh
                        </Button>
                        <Button
                            type="primary"
                            icon={<SaveOutlined />}
                            onClick={handleSave}
                            loading={saving}
                            disabled={!dirty}
                        >
                            Save Changes
                        </Button>
                    </Space>
                }
            >
                {/* Summary cards */}
                <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {familySummary.map(f => (
                        <Tag
                            key={f.family_name}
                            color={SOURCE_COLORS[f.source] || 'default'}
                            style={{ padding: '4px 8px', fontSize: 13 }}
                        >
                            {f.family_name} ({f.column_count})
                        </Tag>
                    ))}
                    {familySummary.length === 0 && !loading && (
                        <Text type="secondary">No families detected. Click "Auto-Detect" to get started.</Text>
                    )}
                </div>

                <Table
                    columns={columns}
                    dataSource={rows}
                    loading={loading}
                    pagination={false}
                    size="small"
                    rowKey="key"
                />
            </Card>

            {/* AI Analysis Modal */}
            <Modal
                title="AI Dimension Family Suggestions"
                open={analyzeModalOpen}
                onCancel={() => setAnalyzeModalOpen(false)}
                width={700}
                footer={[
                    <Button key="cancel" onClick={() => setAnalyzeModalOpen(false)}>Cancel</Button>,
                    <Button key="apply" type="primary" onClick={handleApplySuggestions}>
                        Apply Suggestions
                    </Button>,
                ]}
            >
                {providerUsed && (
                    <Paragraph type="secondary">Provider: {providerUsed}</Paragraph>
                )}
                {llmReasoning && (
                    <Card size="small" style={{ marginBottom: 16 }}>
                        <Text>{llmReasoning}</Text>
                    </Card>
                )}
                <Table
                    dataSource={suggestions.map(s => ({ key: s.family_name, ...s }))}
                    columns={[
                        { title: 'Family', dataIndex: 'family_name', key: 'family_name' },
                        {
                            title: 'Columns',
                            dataIndex: 'columns',
                            key: 'columns',
                            render: (cols: string[]) => cols.map(c => (
                                <Tag key={c} color="purple">{c}</Tag>
                            )),
                        },
                    ]}
                    pagination={false}
                    size="small"
                />
            </Modal>
        </div>
    );
};

export default DimensionFamilies;
