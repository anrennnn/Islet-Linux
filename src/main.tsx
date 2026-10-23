import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Island } from './Island'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Island />
  </StrictMode>
)
