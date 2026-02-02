
import React, { useState } from 'react';
import { Card, Table, Tag, Button, Modal, Input, message, Typography, Row, Col } from 'antd';
import { PlusOutlined, CheckCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPromptVersions, createPromptVersion, activatePromptVersion } from '../services/prompts';
import dayjs from 'dayjs';

const { TextArea } = Input;
const { Text, Title, Paragraph } = Typography;

const Prompts: React.FC = () => {
    const queryClient = useQueryClient();
    const [isModalVisible, setIsModalVisible] = useState(false);
    const [newPrompt, setNewPrompt] = useState('');
    const [newNotes, setNewNotes] = useState('');

    const { data, isLoading } = useQuery({
        queryKey: ['prompts'],
        queryFn: getPromptVersions
    });

    const createMutation = useMutation({
        mutationFn: createPromptVersion,
        onSuccess: () => {
            message.success('New prompt version created');
            setIsModalVisible(false);
            setNewPrompt('');
            setNewNotes('');
            queryClient.invalidateQueries({ queryKey: ['prompts'] });
        },
        onError: (err: any) => message.error(`Failed to create version: ${err.message}`)
    });

    const activateMutation = useMutation({
        mutationFn: activatePromptVersion,
        onSuccess: () => {
            message.success('Prompt version activated');
            queryClient.invalidateQueries({ queryKey: ['prompts'] });
        },
        onError: (err: any) => message.error(`Failed to activate: ${err.message}`)
    });

    const handleCreate = () => {
        if (!newPrompt.trim()) return message.error('Prompt content is required');
        createMutation.mutate({ system_prompt: newPrompt, notes: newNotes });
    };

    const activeVersion = data?.versions.find(v => v.is_active);
    const sortedVersions = data?.versions || [];

    return (
        <div style={{ padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
                <Title level={2}><SafetyCertificateOutlined /> Prompt Management</Title>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalVisible(true)}>
                    New Version
                </Button>
            </div>

            <Row gutter={24}>
                <Col span={14}>
                    <Card title="Version History">
                        <Table
                            loading={isLoading}
                            dataSource={sortedVersions}
                            rowKey="id"
                            pagination={{ pageSize: 5 }}
                            columns={[
                                {
                                    title: 'Ver',
                                    dataIndex: 'version',
                                    width: 80,
                                    render: (v) => <Tag color="blue">v{v}</Tag>
                                },
                                {
                                    title: 'Notes',
                                    dataIndex: 'notes',
                                    render: (notes) => <Text type="secondary">{notes || '-'}</Text>
                                },
                                {
                                    title: 'Created At',
                                    dataIndex: 'created_at',
                                    render: (d) => dayjs(d).format('DD/MM/YYYY HH:mm')
                                },
                                {
                                    title: 'Status',
                                    dataIndex: 'is_active',
                                    width: 120,
                                    render: (isActive) => isActive ?
                                        <Tag icon={<CheckCircleOutlined />} color="success">Active</Tag> :
                                        <Tag color="default">Inactive</Tag>
                                },
                                {
                                    title: 'Action',
                                    key: 'action',
                                    render: (_, record) => (
                                        !record.is_active && (
                                            <Button
                                                size="small"
                                                type="link"
                                                onClick={() => activateMutation.mutate(record.id)}
                                                loading={activateMutation.isPending}
                                            >
                                                Activate
                                            </Button>
                                        )
                                    )
                                }
                            ]}
                        />
                    </Card>
                </Col>
                <Col span={10}>
                    <Card title="Active System Prompt" extra={activeVersion && <Tag color="green">v{activeVersion.version}</Tag>}>
                        {activeVersion ? (
                            <div style={{ maxHeight: '600px', overflowY: 'auto' }}>
                                <Paragraph style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                                    {activeVersion.system_prompt}
                                </Paragraph>
                            </div>
                        ) : (
                            <Text type="secondary">No active prompt version found. Application using default hardcoded prompt.</Text>
                        )}
                    </Card>
                </Col>
            </Row>

            <Modal
                title="Create New Prompt Version"
                open={isModalVisible}
                onOk={handleCreate}
                onCancel={() => setIsModalVisible(false)}
                confirmLoading={createMutation.isPending}
                width={800}
            >
                <div style={{ marginBottom: 16 }}>
                    <label>Description / Release Notes:</label>
                    <Input
                        placeholder="e.g. Improved handling of ambiguous date queries"
                        value={newNotes}
                        onChange={e => setNewNotes(e.target.value)}
                        style={{ marginTop: 8 }}
                    />
                </div>
                <div>
                    <label>System Prompt:</label>
                    <TextArea
                        rows={15}
                        value={newPrompt}
                        onChange={e => setNewPrompt(e.target.value)}
                        placeholder="Enter the full system prompt here..."
                        style={{ marginTop: 8, fontFamily: 'monospace' }}
                    />
                    <Button
                        type="link"
                        onClick={() => setNewPrompt(activeVersion?.system_prompt || '')}
                        disabled={!activeVersion}
                    >
                        Copy from Active Version
                    </Button>
                </div>
            </Modal>
        </div>
    );
};

export default Prompts;
