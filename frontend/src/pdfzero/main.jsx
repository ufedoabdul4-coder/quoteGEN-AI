import React from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import Editor from './pages/Editor.jsx'
import './styles/globals.css'

createRoot(document.getElementById('pdfzero-root')).render(
  <React.StrictMode>
    <Editor />
    <Toaster position="bottom-right" />
  </React.StrictMode>,
)
