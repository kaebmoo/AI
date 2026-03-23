import { useEffect } from 'react'
import { App as AntdApp, Modal as AntdModal, message as antdMessage, notification as antdNotification } from 'antd'

const AntdRuntimeBridge: React.FC = () => {
  const { message, notification, modal } = AntdApp.useApp()

  useEffect(() => {
    Object.assign(antdMessage, message)
    Object.assign(antdNotification, notification)

    AntdModal.info = modal.info
    AntdModal.success = modal.success
    AntdModal.error = modal.error
    AntdModal.warning = modal.warning
    AntdModal.confirm = modal.confirm
  }, [message, notification, modal])

  return null
}

export default AntdRuntimeBridge