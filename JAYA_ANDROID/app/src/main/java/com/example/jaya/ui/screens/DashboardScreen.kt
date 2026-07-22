package com.example.jaya.ui.screens

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.MicOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.jaya.ui.dashboard.DashboardViewModel
import com.example.jaya.ui.dashboard.JarvisState
import androidx.compose.ui.tooling.preview.Preview
import com.example.jaya.ui.theme.JayaTheme

@Composable
fun DashboardScreen(
    modifier: Modifier = Modifier,
    viewModel: DashboardViewModel = viewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val transcribedText by viewModel.lastTranscribedText.collectAsStateWithLifecycle()
    val aiResponse by viewModel.aiResponse.collectAsStateWithLifecycle()

    val audioPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            viewModel.startListening()
        }
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(
                        MaterialTheme.colorScheme.surface,
                        MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
                    )
                )
            )
            .statusBarsPadding()
            .navigationBarsPadding(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                .padding(32.dp)
                .fillMaxWidth()
        ) {
            Text(
                text = "JARVIS SYSTEM",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
                letterSpacing = 4.sp,
                fontWeight = FontWeight.ExtraBold
            )
            
            Spacer(modifier = Modifier.height(64.dp))
            
            JarvisVisualizer(state = state)
            
            Spacer(modifier = Modifier.height(64.dp))
            
            Text(
                text = when (state) {
                    JarvisState.LISTENING -> "LISTENING..."
                    JarvisState.PROCESSING -> "THINKING..."
                    JarvisState.SPEAKING -> "SPEAKING..."
                    JarvisState.ERROR -> "SYSTEM ERROR"
                    else -> "STANDBY"
                },
                style = MaterialTheme.typography.titleMedium,
                color = if (state == JarvisState.ERROR) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.secondary,
                fontWeight = FontWeight.Bold
            )
            
            Spacer(modifier = Modifier.height(24.dp))
            
            if (transcribedText.isNotEmpty()) {
                Text(
                    text = "\"$transcribedText\"",
                    style = MaterialTheme.typography.bodyLarge,
                    textAlign = TextAlign.Center,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            if (aiResponse.isNotEmpty()) {
                Surface(
                    color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.5f),
                    shape = MaterialTheme.shapes.medium,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = aiResponse,
                        style = MaterialTheme.typography.bodyMedium,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(16.dp)
                    )
                }
            }
            
            Spacer(modifier = Modifier.weight(1f))
            
            FloatingActionButton(
                onClick = {
                    if (state == JarvisState.LISTENING) {
                        viewModel.stopListening()
                    } else {
                        audioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    }
                },
                containerColor = if (state == JarvisState.LISTENING) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
                shape = CircleShape,
                modifier = Modifier.size(80.dp)
            ) {
                Icon(
                    imageVector = if (state == JarvisState.LISTENING) Icons.Rounded.MicOff else Icons.Rounded.Mic,
                    contentDescription = "Voice Interaction",
                    modifier = Modifier.size(32.dp)
                )
            }
        }
    }
}

@Composable
fun JarvisVisualizer(state: JarvisState) {
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val scale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = if (state == JarvisState.LISTENING || state == JarvisState.SPEAKING) 1.2f else 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "scale"
    )
    
    val rotation by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            animation = tween(if (state == JarvisState.PROCESSING) 2000 else 8000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "rotation"
    )

    Box(contentAlignment = Alignment.Center) {
        // Outer glow
        Surface(
            modifier = Modifier
                .size(160.dp)
                .scale(scale),
            shape = CircleShape,
            color = when (state) {
                JarvisState.LISTENING -> MaterialTheme.colorScheme.primary.copy(alpha = 0.2f)
                JarvisState.PROCESSING -> MaterialTheme.colorScheme.tertiary.copy(alpha = 0.2f)
                JarvisState.SPEAKING -> MaterialTheme.colorScheme.secondary.copy(alpha = 0.2f)
                JarvisState.ERROR -> MaterialTheme.colorScheme.error.copy(alpha = 0.2f)
                else -> MaterialTheme.colorScheme.outline.copy(alpha = 0.1f)
            }
        ) {}
        
        // Main Circle
        Surface(
            modifier = Modifier
                .size(120.dp)
                .graphicsLayer { rotationZ = rotation },
            shape = CircleShape,
            color = Color.Transparent,
            border = androidx.compose.foundation.BorderStroke(
                4.dp, 
                Brush.sweepGradient(
                    listOf(
                        MaterialTheme.colorScheme.primary,
                        MaterialTheme.colorScheme.secondary,
                        MaterialTheme.colorScheme.primary
                    )
                )
            )
        ) {
            Box(
                modifier = Modifier.fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                // Spinning element
                Box(
                    modifier = Modifier
                        .size(80.dp)
                        .scale(if (state == JarvisState.PROCESSING) 1.5f else 1f)
                        .background(
                            Brush.linearGradient(
                                listOf(
                                    MaterialTheme.colorScheme.primary.copy(alpha = 0.5f),
                                    MaterialTheme.colorScheme.secondary.copy(alpha = 0.5f)
                                )
                            ),
                            shape = CircleShape
                        )
                )
            }
        }
    }
}

@Preview(showBackground = true, showSystemUi = true)
@Composable
fun DashboardScreenPreview() {
    JayaTheme {
        DashboardScreen()
    }
}
