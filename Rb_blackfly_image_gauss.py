from PIL import Image
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import io
import os

#module for image processing for the blackfly camera


#the number of microns per pixel:
um = 3.75

#1D gaussian fit
def gaussian(arr, a, mu, sigma, b):
	return a*np.exp(-(arr-mu)**2/(2*sigma**2)) + b

#fit of five gaussian peaks
def five_gaussians(arr, a1, mu1, sigma1, a2, mu2, sigma2, a3, mu3, sigma3, a4, mu4, sigma4, a5, mu5, sigma5, b):
        return (gaussian(arr, a1, mu1, sigma1, b=0) +
        gaussian(arr, a2, mu2, sigma2, b=0) +
        gaussian(arr, a3, mu3, sigma3, b=0) +
        gaussian(arr, a4, mu4, sigma4, b=0) +
        gaussian(arr, a5, mu5, sigma5, b=0) + b)

def gnd_gauss(arr):
    #fitting the ground image to a gaussian:
    x, y = arr.shape
    yArray = np.zeros(x)
    xArray = np.zeros(y)
    #sum of each column into rows:
    for i in range(0, x):
        yArray[i] = sum(arr[i,:])
    #sum of each row into columns:
    for i in range(0, y):
        xArray[i] = sum(arr[:,i])
    yAxis = np.linspace(0, x-1, x)
    xAxis = np.linspace(0, y-1, y)
	#making the guess
    maxPos = np.argmax(xArray)
    maxInt = np.amax(xArray)
    guessx = np.array([maxInt, maxPos, 50, 0])
    maxPos = np.argmax(yArray)
    maxInt = np.amax(yArray)
    guessy = np.array([maxInt, maxPos, 50, 0])

    popty, pcovy = curve_fit(gaussian, yAxis, yArray, guessy)
    poptx, pcovx = curve_fit(gaussian, xAxis, xArray, guessx)

    pos = {'x': poptx[1], 'y': popty[1]}
    return pos

def fort_gauss(arr):
    x, y = arr.shape
    yArray = np.zeros(x)
    xArray = np.zeros(y)
    for i in range(0, x):
        yArray[i] = sum(arr[i,:])
    for i in range(0, y):
        xArray[i] = sum(arr[:,i])
    yAxis = np.linspace(0, x-1, x)
    xAxis = np.linspace(0, y-1, y)
	#generating guesses
    maxPos = np.argmax(xArray)
    maxInt = np.amax(xArray)
    guessx = np.array([maxInt, maxPos-(37*2), 10, maxInt, maxPos-37, 10, maxInt, maxPos, 10, maxInt, maxPos+37, 10, maxInt, maxPos+(37*2), 10, 0])
    maxPos = np.argmax(yArray)
    maxInt = np.amax(yArray)
    guessy = np.array([maxInt, maxPos, 30, 0])
    #fitting the projections
    popty, pcovy = curve_fit(gaussian, yAxis, yArray, guessy)
    poptx, pcovx = curve_fit(five_gaussians, xAxis, xArray, guessx)
    px = five_gaussians(xAxis, *poptx)
    #plt.plot(xAxis, xArray) #suppresed plotting
    #plt.show()
    pos = {'x': poptx[7], 'y': popty[1]}
    return pos
